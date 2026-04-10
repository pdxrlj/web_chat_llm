"""核心记忆系统实现"""

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, List, Optional

import torch
from openai import AsyncOpenAI

from .conflict_resolver import ConflictResolver
from .models import ConflictResolution, MemoryItem, MemoryType
from .storage import BaseStorage

logger = logging.getLogger(__name__)


class AsyncMemory:
    """
    高性能异步记忆系统

    特性：
    - 异步 API，高性能低延迟
    - 智能冲突检测和合并
    - 本地 embedding 和 reranker（默认 CUDA 加速）
    - 自动提取实体和关键词
    - 支持 Qwen 的 enable_thinking 参数

    使用示例：
        # 从 config.yaml 加载
        memory = AsyncMemory.from_config("qwen")

        # 添加记忆
        await memory.add(
            messages=[{"role": "user", "content": "我喜欢跑步"}],
            user_id="user_123",
        )

        # 检索记忆
        results = await memory.search("运动", user_id="user_123")
    """

    @classmethod
    def from_config(
        cls,
        llm_name: str = "memory",  # 修改默认LLM为memory配置
        storage: Optional[BaseStorage] = None,
        conflict_resolution: ConflictResolution = ConflictResolution.MERGE,
        enable_conflict_detection: bool = True,
        similarity_threshold: float = 0.7,
        enable_thinking: bool = False,
        embedding_model: Optional[str] = None,
        reranker_model: Optional[str] = None,
        device: str = "cuda",
    ) -> "AsyncMemory":
        """
        从 config.yaml 创建 AsyncMemory 实例

        Args:
            llm_name: config.yaml 中的 LLM 配置名称
            storage: 存储后端（必填，必须提供 MilvusStorage 实例）
            conflict_resolution: 冲突解决策略
            enable_conflict_detection: 是否启用冲突检测
            similarity_threshold: 冲突检测的相似度阈值
            enable_thinking: 是否启用 Qwen 的思考模式
            embedding_model: 本地 embedding 模型名称（可选，从配置读取）
            reranker_model: 本地 reranker 模型名称（可选，从配置读取）
            device: 设备类型（默认 cuda）

        Returns:
            AsyncMemory 实例
        """
        from core.config import config as app_config

        llm_config = app_config.get_llm(llm_name)
        if not llm_config:
            raise ValueError(f"未找到 LLM 配置: {llm_name}")

        if storage is None:
            raise ValueError("storage 参数必填，必须提供 MilvusStorage 实例")

        # 从配置文件读取本地模型配置
        if embedding_model is None:
            try:
                embedding_config = app_config.get_embedding("local_embedding")
                if embedding_config:
                    embedding_model = embedding_config.model
                else:
                    embedding_model = "BAAI/bge-base-en-v1.5"
            except Exception:
                embedding_model = "BAAI/bge-base-en-v1.5"

        if reranker_model is None:
            try:
                reranker_config = app_config.get_embedding("reranker")
                if reranker_config:
                    reranker_model = reranker_config.model
                else:
                    reranker_model = "BAAI/bge-reranker-v2-m3"
            except Exception:
                reranker_model = "BAAI/bge-reranker-v2-m3"

        logger.info(f"使用 LLM: {llm_config.model}")
        logger.info(f"使用设备: {device}")
        logger.info(f"Embedding 模型: {embedding_model}")
        logger.info(f"Reranker 模型: {reranker_model}")

        return cls(
            openai_api_key=llm_config.api_key,
            openai_base_url=llm_config.base_url,
            openai_model=llm_config.model,
            embedding_model=embedding_model,
            reranker_model=reranker_model,
            storage=storage,
            conflict_resolution=conflict_resolution,
            enable_conflict_detection=enable_conflict_detection,
            similarity_threshold=similarity_threshold,
            enable_thinking=enable_thinking,
            device=device,
        )

    def __init__(
        self,
        openai_api_key: str,
        openai_base_url: str = "https://api.openai.com/v1",
        openai_model: str = "gpt-4o-mini",
        embedding_model: str = "BAAI/bge-base-en-v1.5",
        reranker_model: str = "BAAI/bge-reranker-v2-m3",
        storage: Optional[BaseStorage] = None,
        conflict_resolution: ConflictResolution = ConflictResolution.MERGE,
        enable_conflict_detection: bool = True,
        similarity_threshold: float = 0.7,
        enable_thinking: bool = False,
        device: str = "cuda",
    ):
        """
        初始化记忆系统

        Args:
            openai_api_key: OpenAI API Key
            openai_base_url: OpenAI API 基础 URL
            openai_model: 用于记忆提取和冲突合并的模型
            embedding_model: 本地 embedding 模型名称
            reranker_model: 本地 reranker 模型名称
            storage: 存储后端（必填，必须提供 MilvusStorage 实例）
            conflict_resolution: 冲突解决策略
            enable_conflict_detection: 是否启用冲突检测
            similarity_threshold: 冲突检测的相似度阈值
            enable_thinking: Qwen 的思考模式
            device: 设备类型（cuda 或 cpu，默认 cuda）
        """
        if storage is None:
            raise ValueError("storage 参数必填，必须提供 MilvusStorage 实例")

        # 检测 CUDA 是否可用
        self._check_cuda_available(device)

        # OpenAI 客户端
        self.openai_client = AsyncOpenAI(
            api_key=openai_api_key,
            base_url=openai_base_url,
        )

        # 配置
        self.openai_model = openai_model
        self.embedding_model = embedding_model
        self.reranker_model = reranker_model
        self.conflict_resolution = conflict_resolution
        self.enable_conflict_detection = enable_conflict_detection
        self.similarity_threshold = similarity_threshold
        self.enable_thinking = enable_thinking
        self.device = device

        # 本地模型实例（延迟加载）
        self._embedding_model_instance = None
        self._reranker_model_instance = None

        # 存储层
        self.storage = storage

        # 冲突解决器
        self.conflict_resolver = ConflictResolver(
            openai_client=self.openai_client,
            model=openai_model,
            enable_thinking=enable_thinking,
        )

    def _check_cuda_available(self, device: str) -> None:
        """检测 CUDA 是否可用"""
        if device == "cuda":
            if not torch.cuda.is_available():
                raise RuntimeError(
                    "CUDA 不可用！请确保已正确安装 CUDA 和 GPU 驱动。\n"
                    "可用的 GPU: 无\n"
                    "PyTorch 版本: " + torch.__version__
                )
            logger.info(f"CUDA 可用，检测到 GPU: {torch.cuda.get_device_name(0)}")
            logger.info(f"GPU 数量: {torch.cuda.device_count()}")

    async def warm_up(
        self, load_embedding: bool = True, load_reranker_model: bool = False
    ):
        """
        预热模型，提前加载以避免首次调用时的延迟

        Args:
            load_embedding: 是否预加载 embedding 模型（默认 True）
            load_reranker_model: 是否预加载 reranker 模型（默认 False）
        """
        import asyncio

        tasks = []

        if load_embedding and self._embedding_model_instance is None:
            logger.info("预热 Embedding 模型...")
            # 使用简单的测试文本触发模型加载
            tasks.append(self._get_embedding("warm up"))

        if load_reranker_model and self._reranker_model_instance is None:
            logger.info("预热 Reranker 模型...")

            # 创建一个假的搜索结果来触发 reranker 加载
            async def trigger_reranker():
                from .models import MemoryItem

                fake_memory = MemoryItem(
                    id="warm_up", content="warm up", user_id="system"
                )
                await self._rerank_results("warm up", [(fake_memory, 0.9)], top_k=1)

            tasks.append(trigger_reranker())

        if tasks:
            await asyncio.gather(*tasks)
            logger.info("模型预热完成")

    async def add(
        self,
        messages: List[Dict[str, str]],
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        infer: bool = True,
        auto_detect_conflict: bool = True,
        flush_after: bool = False,  # 新增参数：是否在添加后立即flush
    ) -> Dict[str, Any]:
        """
        添加记忆

        Args:
            messages: 对话消息列表
            user_id: 用户 ID
            session_id: 会话 ID
            metadata: 自定义元数据
            infer: 是否使用 LLM 提取记忆（False 则直接存储原始消息）
            auto_detect_conflict: 是否自动检测冲突
            flush_after: 是否在添加后立即flush到磁盘，确保数据可见性（默认False，提高性能）

        Returns:
            添加结果，包含记忆 ID 和冲突信息
        """
        import time

        method_start_time = time.time()

        logger.info(f"开始添加记忆，消息数: {len(messages)}, infer: {infer}")

        # 1. 提取记忆
        extract_start = time.time()
        if infer:
            memory_items = await self._extract_memories(messages, user_id, session_id)
        else:
            # 直接存储消息
            memory_items = [
                MemoryItem(
                    id=str(uuid.uuid4()),
                    content=msg["content"],
                    user_id=user_id,
                    session_id=session_id,
                    metadata=metadata or {},
                )
                for msg in messages
                if msg.get("content")
            ]
        extract_time = time.time() - extract_start
        logger.info(
            f"提取记忆完成，耗时: {extract_time:.3f} 秒，记忆数: {len(memory_items)}"
        )

        # 2. 为每个记忆生成嵌入
        embed_start = time.time()
        for item in memory_items:
            item.embedding = await self._get_embedding(item.content)
        embed_time = time.time() - embed_start
        logger.info(f"生成嵌入完成，耗时: {embed_time:.3f} 秒")

        # 3. 检测和处理冲突
        conflict_start = time.time()
        conflicts_detected = []
        actually_added = 0  # 实际存储的记忆数
        for item in memory_items:
            logger.info(f"处理记忆: {item.content[:50]}...")

            # 检查 embedding 是否存在
            if not item.embedding:
                logger.warning(f"  记忆缺少 embedding，直接存储")
                await self.storage.add(item)
                actually_added += 1
                continue

            if auto_detect_conflict and self.enable_conflict_detection:
                # 搜索相关记忆（取top_k条，用宽松阈值初筛）
                similar_memories = await self.storage.search_by_embedding(
                    embedding=item.embedding,
                    top_k=10,
                    user_id=user_id,
                )

                logger.info(f"  搜索到 {len(similar_memories)} 条候选记忆")
                for mem, sim in similar_memories[:8]:
                    logger.info(
                        f"    候选: sim={sim:.4f}, content='{mem.content[:40]}', "
                        f"type={mem.memory_type.value}"
                    )

                # 简化策略：只要有候选记忆，就全部交给 LLM 判断
                # 去掉复杂的向量阈值/实体匹配/字符重叠等预筛选
                # LLM 本身就能理解语义关系，不需要规则预判
                if not similar_memories:
                    logger.info(f"  无任何相关记忆，直接添加")
                    await self.storage.add(item)
                    actually_added += 1
                    continue

                logger.info(f"  将 {len(similar_memories)} 条候选交由 LLM 分析...")

                # 让 LLM 综合分析，决定操作类型（新增/修改/合并/删除/跳过）
                from .conflict_resolver import MemoryAction

                action, merged_content, ids_to_delete = (
                    await self.conflict_resolver.evaluate_memory(item, similar_memories)
                )

                logger.info(f"  LLM 处理动作: {action.value}")

                if action == MemoryAction.MERGE and merged_content:
                    # 合并：删除旧记忆，添加合并后的
                    conflicts_detected.append(
                        {"action": "merge", "content": merged_content}
                    )
                    if ids_to_delete:
                        for mid in ids_to_delete:
                            await self.storage.delete(mid)
                            logger.info(f"  已删除记忆: {mid}")

                    merged_memory = MemoryItem(
                        id=str(uuid.uuid4()),
                        content=merged_content,
                        memory_type=item.memory_type,
                        user_id=user_id,
                        session_id=session_id,
                        embedding=item.embedding,
                    )
                    await self.storage.add(merged_memory)
                    actually_added += 1
                    logger.info(f"  已存储合并记忆: {merged_content[:50]}...")

                elif action == MemoryAction.REPLACE:
                    # 替换：删除指定的旧记忆，添加新记忆
                    conflicts_detected.append({"action": "replace"})
                    if ids_to_delete:
                        for mid in ids_to_delete:
                            await self.storage.delete(mid)
                            logger.info(f"  已删除记忆: {mid}")
                    else:
                        for mem, _ in similar_memories:
                            await self.storage.delete(mem.id)
                            logger.info(f"  已删除记忆: {mem.id}")

                    await self.storage.add(item)
                    actually_added += 1
                    logger.info(f"  已存储新记忆: {item.content[:50]}...")

                elif action == MemoryAction.REJECT:
                    # 拒绝：跳过新记忆
                    conflicts_detected.append({"action": "reject"})
                    logger.info(f"  拒绝新记忆（无新信息）")

                else:
                    # APPEND：直接添加
                    await self.storage.add(item)
                    actually_added += 1
                    logger.info(f"  直接存储新记忆")
            else:
                # 不检测冲突，直接存储
                await self.storage.add(item)
                actually_added += 1
                logger.info(f"  跳过冲突检测，直接存储")
        conflict_time = time.time() - conflict_start
        logger.info(
            f"冲突检测和存储完成，耗时: {conflict_time:.3f} 秒，冲突数: {len(conflicts_detected)}"
        )

        # 计算总耗时
        method_total_time = time.time() - method_start_time

        # 如果需要，在添加后立即flush
        if flush_after:
            flush_start = time.time()
            await self.storage._connect()
            await self.storage.flush()
            flush_time = time.time() - flush_start
            logger.info(f"手动flush完成，耗时: {flush_time:.3f} 秒")
            conflict_time += flush_time  # 将flush时间包含在冲突处理时间内
            method_total_time += flush_time  # 更新总耗时
        logger.info(f"添加记忆完成，总耗时: {method_total_time:.3f} 秒")

        return {
            "status": "success",
            "memories_extracted": len(memory_items),  # LLM 提取的记忆数
            "memories_added": actually_added,  # 实际存储的记忆数
            "memory_ids": [m.id for m in memory_items],
            "conflicts_detected": conflicts_detected,
            "timing": {
                "extract": extract_time,
                "embed": embed_time,
                "conflict": conflict_time,
                "total": method_total_time,
            },
        }

    async def search(
        self,
        query: str,
        user_id: Optional[str] = None,
        top_k: int = 10,
        use_reranker: bool = True,
    ) -> Dict[str, Any]:
        """
        检索记忆

        Args:
            query: 查询文本
            user_id: 用户 ID（可选，用于过滤）
            top_k: 返回数量
            use_reranker: 是否使用 reranker（默认 True）

        Returns:
            检索结果
        """
        import time

        method_start_time = time.time()

        logger.info(
            f"开始搜索记忆，查询: {query[:50]}..., top_k: {top_k}, use_reranker: {use_reranker}"
        )

        # 1. 生成查询嵌入
        embed_start = time.time()
        query_embedding = await self._get_embedding(query)
        embed_time = time.time() - embed_start
        logger.info(f"生成查询嵌入完成，耗时: {embed_time:.3f} 秒")

        # 2. 向量检索（取更多候选，用于 reranker 过滤）
        search_start = time.time()
        candidate_count = top_k * 3 if use_reranker else top_k
        results = await self.storage.search_by_embedding(
            embedding=query_embedding,
            top_k=candidate_count,
            user_id=user_id,
        )
        search_time = time.time() - search_start
        logger.info(f"向量检索完成，耗时: {search_time:.3f} 秒，候选数: {len(results)}")

        # 3. 如果启用 reranker，进行重排序
        rerank_time = 0.0
        if use_reranker:
            rerank_start = time.time()
            results = await self._rerank_results(query, results, top_k)
            rerank_time = time.time() - rerank_start
            logger.info(f"结果重排序完成，耗时: {rerank_time:.3f} 秒")

        # 4. 格式化结果
        format_start = time.time()
        memories = [
            {
                "id": memory.id,
                "content": memory.content,
                "user_id": memory.user_id,
                "created_at": memory.created_at.isoformat(),
                "score": score,
            }
            for memory, score in results[:top_k]
        ]
        format_time = time.time() - format_start

        method_total_time = time.time() - method_start_time
        logger.info(
            f"搜索完成，总耗时: {method_total_time:.3f} 秒，返回结果数: {len(memories)}"
        )

        return {
            "query": query,
            "results": memories,
            "total": len(memories),
            "timing": {
                "embed": embed_time,
                "search": search_time,
                "rerank": rerank_time,
                "format": format_time,
                "total": method_total_time,
            },
        }

    async def _rerank_results(
        self,
        query: str,
        results: List[tuple],
        top_k: int,
    ) -> List[tuple]:
        """使用本地 reranker 对结果重排序"""

        if not results:
            return results

        # 延迟加载 reranker 模型
        if self._reranker_model_instance is None:
            from sentence_transformers import CrossEncoder

            logger.info(f"加载 Reranker 模型: {self.reranker_model} 到 {self.device}")
            self._reranker_model_instance = CrossEncoder(
                self.reranker_model,
                device=self.device,
                cache_folder="./models",
            )

        # 准备候选文档
        documents = [memory.content for memory, _ in results]

        # 使用 reranker 打分
        assert self._reranker_model_instance is not None
        reranker = self._reranker_model_instance
        loop = asyncio.get_event_loop()
        scores = await loop.run_in_executor(
            None,
            lambda: reranker.predict([(query, doc) for doc in documents]),
        )

        # 根据新分数重新排序
        reranked = sorted(zip(results, scores), key=lambda x: x[1], reverse=True)

        # 返回 top_k 结果
        return [(memory, score) for (memory, _), score in reranked[:top_k]]

    async def get_all(
        self,
        user_id: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """
        获取所有记忆

        Args:
            user_id: 用户 ID（可选）
            limit: 返回数量限制

        Returns:
            记忆列表
        """
        memories = await self.storage.get_all(user_id=user_id, limit=limit)

        return {
            "memories": [m.to_dict() for m in memories],
            "total": len(memories),
        }

    async def delete(self, memory_id: str) -> Dict[str, Any]:
        """
        删除记忆

        Args:
            memory_id: 记忆 ID

        Returns:
            删除结果
        """
        success = await self.storage.delete(memory_id)

        return {
            "status": "success" if success else "failed",
            "memory_id": memory_id,
        }

    async def organize(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        整理记忆：遍历所有记忆，检测并解决冲突。

        Args:
            user_id: 用户 ID（可选，为空则整理全部）

        Returns:
            整理结果
        """
        from .conflict_resolver import MemoryAction

        memories = await self.storage.get_all(user_id=user_id, limit=500)
        conflicts_resolved = 0
        memories_deleted = 0

        for memory in memories:
            if not memory.embedding:
                continue

            similar = await self.storage.search_by_embedding(
                embedding=memory.embedding,
                top_k=5,
                user_id=user_id,
            )

            # 过滤掉自己
            similar = [(m, s) for m, s in similar if m.id != memory.id]

            if similar:
                action, merged_content, ids_to_delete = (
                    await self.conflict_resolver.evaluate_memory(memory, similar)
                )

                if action == MemoryAction.MERGE and merged_content:
                    # 删除需要删除的记忆
                    if ids_to_delete:
                        for mid in ids_to_delete:
                            await self.storage.delete(mid)
                            memories_deleted += 1

                    # 更新当前记忆
                    memory.content = merged_content
                    await self.storage.update(memory)
                    conflicts_resolved += 1

                elif action == MemoryAction.REPLACE:
                    # 删除相似记忆
                    for m, _ in similar:
                        await self.storage.delete(m.id)
                        memories_deleted += 1
                    conflicts_resolved += 1

                elif action == MemoryAction.REJECT:
                    # 删除当前记忆（重复）
                    await self.storage.delete(memory.id)
                    memories_deleted += 1
                    conflicts_resolved += 1

        return {
            "status": "success",
            "total_scanned": len(memories),
            "conflicts_resolved": conflicts_resolved,
            "memories_deleted": memories_deleted,
        }

    # ========== 内部方法 ==========

    async def _extract_memories(
        self,
        messages: List[Dict[str, str]],
        user_id: Optional[str],
        session_id: Optional[str],
    ) -> List[MemoryItem]:
        """使用 LLM 从对话中提取记忆"""

        prompt = f"""从以下对话中提取关于用户的重要记忆事实。

对话：
{json.dumps(messages, ensure_ascii=False, indent=2)}

**重要说明**：
1. 只从 role="user" 的消息中提取用户的偏好、事实、事件
2. role="assistant" 的回复只是对话上下文，**不要**将其内容或风格当作用户的偏好
3. 如果用户在回复中确认了某些信息（如"是的"、"对的"），可以提取该信息
4. 过滤掉无关紧要的寒暄和礼貌用语

提取要求：
1. 提取用户偏好、重要事件、关键事实信息
2. 每条记忆应该简洁明确，**不要添加任何前缀、标签或元数据**
3. 确保提取的是用户的信息，而不是助手的表现或风格
4. **content 字段只包含简洁的事实陈述，不要包含"标签:"等额外信息**
5. **【关键】必须保留情感和态度词汇！对于偏好类记忆（preference），content 中必须包含"喜欢/不喜欢/爱/讨厌/想/不想"等情感词**

请返回 JSON 格式：
{{
    "memories": [
        {{
            "content": "简洁的记忆内容（保留原始态度词：喜欢/不喜欢/爱/讨厌等）",
            "type": "fact/preference/event/context",
            "entities": ["实体1", "实体2"],
            "keywords": ["关键词1", "关键词2"]
        }}
    ]
}}

类型说明：
- fact: 事实信息（如：姓名、职业、年龄）
- preference: 用户偏好（如：喜欢、不喜欢、习惯）— **必须包含情感方向词**
- event: 发生的事件（如：搬家、换工作）
- context: 对话背景（如：当前情境、环境信息）

**正确示例**：
对话：
[
  {{"role": "user", "content": "我不喜欢颜文字"}},
  {{"role": "assistant", "content": "嘿嘿～好的！"}}
]
提取结果：
{{
    "content": "不喜欢颜文字",
    "type": "preference",
    "entities": ["颜文字"],
    "keywords": ["不喜欢", "颜文字"]
}}

**错误示例**（避免以下问题）：
{{"content": "用户不喜欢颜文字", ...}}  （不要加"用户"前缀）
{{"content": "不喜欢颜文字, 标签: 不喜欢", ...}}  （不要在 content 中包含标签信息）
{{"content": "用户喜欢颜文字和表情", ...}}  （这是助手的表现，不是用户的偏好）
{{"content": "每天吃苹果", ...}}  （丢失了"喜欢"这个关键情感词！）

**更多示例**：

对话：[{{"role": "user", "content": "我喜欢吃苹果"}}]
提取：{{"content": "喜欢吃苹果", "type": "preference", "entities": ["苹果"], "keywords": ["喜欢", "苹果"]}}
（注意：保留了"喜欢"，不能只写"吃苹果"或"每天吃苹果"）

对话：[{{"role": "user", "content": "我很喜欢吃苹果，每天都要吃一个"}}]
提取：{{"content": "很喜欢吃苹果，每天都吃一个", "type": "preference", "entities": ["苹果"], "keywords": ["很", "喜欢", "吃", "苹果"]}}
（注意："很"+"喜欢"是情感强度+方向，必须保留！不能简化为"每天吃一个苹果"）

对话：[{{"role": "user", "content": "其实我最近不喜欢吃苹果了，感觉太甜了"}}]
提取：{{"content": "最近不喜欢吃苹果，感觉太甜", "type": "preference", "entities": ["苹果"], "keywords": ["不喜欢", "苹果", "太甜"]}}
（注意：保留了"不喜欢"+原因"太甜"）

对话：[{{"role": "user", "content": "我住在上海"}}]
提取：{{"content": "住在上海", "type": "fact", "entities": ["上海"], "keywords": ["住", "上海"]}}

对话：[{{"role": "user", "content": "我最近搬家了"}}]
提取：{{"content": "最近搬家了", "type": "event", "entities": [], "keywords": ["搬家"]}}

**【最高优先级规则】**：
- 当用户表达喜好/厌恶时，content 必须包含"喜欢/不爱/讨厌/想/不想"等词
- 这些情感词是后续冲突检测的基础，绝对不能省略
- 宁可 content 稍长一些，也不能丢失情感方向信息
"""

        try:
            # 构建请求参数
            request_params = {
                "model": self.openai_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
            }

            request_params["extra_body"] = {
                "enable_thinking": False
            }  # 强制禁用思考模式

            response = await self.openai_client.chat.completions.create(
                **request_params
            )

            result = json.loads(response.choices[0].message.content)

            memories = []
            for item in result.get("memories", []):
                # 安全地解析记忆类型，如果无效则使用默认值FACT
                memory_type_str = item.get("type", "fact")
                try:
                    memory_type = MemoryType(memory_type_str)
                except ValueError:
                    # 处理无效的记忆类型，使用默认值FACT
                    logger.warning(f"无效的记忆类型: {memory_type_str}, 使用默认值FACT")
                    memory_type = MemoryType.FACT

                # 清理和规范化 content
                content = item["content"].strip()

                # 移除可能的"用户"前缀（如果 LLM 仍然添加了）
                if content.startswith("用户"):
                    content = content[2:].strip()

                # 移除可能的标签信息（如果 LLM 混入了）
                if ", 标签:" in content or "，标签：" in content:
                    content = content.split(", 标签:")[0].split("，标签：")[0].strip()

                # 确保 content 不为空
                if not content:
                    logger.warning(f"提取的记忆内容为空，跳过")
                    continue

                memory = MemoryItem(
                    id=str(uuid.uuid4()),
                    content=content,
                    memory_type=memory_type,
                    user_id=user_id,
                    session_id=session_id,
                    entities=item.get("entities", []),
                    keywords=item.get("keywords", []),
                )
                memories.append(memory)

            logger.info(f"成功提取 {len(memories)} 条记忆")
            return memories

        except Exception as e:
            logger.error(f"提取记忆失败: {e}")
            # 失败时返回原始消息
            return [
                MemoryItem(
                    id=str(uuid.uuid4()),
                    content=msg["content"],
                    user_id=user_id,
                    session_id=session_id,
                )
                for msg in messages
                if msg.get("content")
            ]

    async def _get_embedding(self, text: str) -> List[float]:
        """使用本地模型获取向量嵌入"""

        try:
            # 延迟加载本地模型
            if self._embedding_model_instance is None:
                from sentence_transformers import SentenceTransformer

                logger.info(
                    f"加载 Embedding 模型: {self.embedding_model} 到 {self.device}"
                )
                self._embedding_model_instance = SentenceTransformer(
                    self.embedding_model,
                    device=self.device,
                    cache_folder="./models",
                    # 禁用远程检查和更新
                    use_auth_token=False,
                    trust_remote_code=False,
                )

            # 生成向量
            assert self._embedding_model_instance is not None
            embedder = self._embedding_model_instance
            loop = asyncio.get_event_loop()
            embedding = await loop.run_in_executor(
                None,
                lambda: embedder.encode(text, convert_to_tensor=False).tolist(),
            )

            return embedding

        except Exception as e:
            logger.error(f"获取嵌入失败: {e}")
            raise RuntimeError(f"获取嵌入失败: {e}")

    def _is_potential_conflict(
        self, new_item: MemoryItem, existing: MemoryItem
    ) -> bool:
        """
        判断两条记忆是否可能是潜在冲突（基于实体和类型匹配）

        即使向量相似度不高，只要实体重叠+类型相同，就可能是冲突
        例如： "很喜欢吃苹果" vs "不喜欢吃苹果" — 实体都是[苹果]，类型都是preference

        Args:
            new_item: 新记忆
            existing: 已有记忆

        Returns:
            是否可能是潜在冲突
        """
        # 类型必须相同（preference vs preference, fact vs fact）
        if new_item.memory_type != existing.memory_type:
            return False

        # 至少有一个共同实体或关键词
        new_tags = set(new_item.entities) | set(new_item.keywords)
        existing_tags = set(existing.entities) | set(existing.keywords)

        if new_tags and existing_tags:
            overlap = new_tags & existing_tags
            if len(overlap) > 0:
                return True

        # 兜底：使用字符级中文重叠检测
        # 原因：旧记录从 Milvus 读取时 entities/keywords 为空，
        # 且整句中文无空格分隔，正则 \w+ 会把整句当做一个"词"
        import re as _re

        new_chars = set(_re.findall(r"[\u4e00-\u9fff]", new_item.content))
        existing_chars = set(_re.findall(r"[\u4e00-\u9fff]", existing.content))

        if new_chars and existing_chars:
            overlap_chars = new_chars & existing_chars
            # 至少共享3个汉字才算相关主题
            # 例如："喜欢吃苹果"(4字) vs "不喜欢吃苹果"(5字) → 共享"吃苹果"(3字)
            return len(overlap_chars) >= 3

        return False

    async def _detect_conflict_for_new_memory(
        self,
        new_memory: MemoryItem,
        user_id: Optional[str],
    ) -> Optional[Any]:
        """为新记忆检测冲突"""

        if not new_memory.embedding:
            return None

        # 检索相似记忆
        similar_memories = await self.storage.search_by_embedding(
            embedding=new_memory.embedding,
            top_k=5,
            user_id=user_id,
        )

        # 检查每个相似记忆是否存在冲突
        for old_memory, similarity in similar_memories:
            logger.info(
                f"  检测相似记忆 - 相似度: {similarity:.4f}, 阈值: {self.similarity_threshold}, "
                f"内容: {old_memory.content[:30]}..."
            )
            if similarity >= self.similarity_threshold:
                conflict = await self.conflict_resolver.detect_conflict(
                    old_memory,
                    new_memory,
                    self.similarity_threshold,
                    similarity_score=similarity,  # 传递相似度分数
                )

                if conflict:
                    logger.info(
                        f"  ✓ 需要处理 - 相似度: {similarity:.4f}, 类型: {conflict.conflict_type}"
                    )
                    return conflict
            else:
                # 相似度不够，后续的记忆更不可能满足阈值
                logger.info(
                    f"  ✗ 相似度 {similarity:.4f} 低于阈值 {self.similarity_threshold}，停止检测"
                )
                break

        logger.info(f"  未找到冲突（相似度都不足或 LLM 判断无冲突）")
        return None
