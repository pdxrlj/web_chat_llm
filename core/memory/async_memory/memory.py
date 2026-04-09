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
        similarity_threshold: float = 0.85,
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
        similarity_threshold: float = 0.85,
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
                # 搜索相似记忆
                similar_memories = await self.storage.search_by_embedding(
                    embedding=item.embedding,
                    top_k=100,
                    user_id=user_id,
                )

                if similar_memories:
                    # 打印相似记忆
                    for mem, sim in similar_memories[:3]:
                        logger.info(f"  相似记忆: {sim:.4f} - {mem.content[:40]}...")

                    # 让 LLM 评估如何处理
                    from .conflict_resolver import MemoryAction

                    action, merged_content, ids_to_delete = (
                        await self.conflict_resolver.evaluate_memory(
                            item, similar_memories
                        )
                    )

                    logger.info(f"  处理动作: {action.value}")

                    if action == MemoryAction.MERGE and merged_content:
                        # 合并：删除旧记忆，添加合并后的
                        conflicts_detected.append(
                            {"action": "merge", "content": merged_content}
                        )

                        # 删除需要删除的记忆
                        if ids_to_delete:
                            for mid in ids_to_delete:
                                await self.storage.delete(mid)
                                logger.info(f"  已删除记忆: {mid}")

                        # 创建合并后的记忆
                        merged_memory = MemoryItem(
                            id=str(uuid.uuid4()),
                            content=merged_content,
                            memory_type=item.memory_type,
                            user_id=user_id,
                            session_id=session_id,
                            embedding=item.embedding,  # 暂用新记忆的embedding
                        )
                        await self.storage.add(merged_memory)
                        actually_added += 1
                        logger.info(f"  已存储合并记忆: {merged_content[:50]}...")

                    elif action == MemoryAction.REPLACE:
                        # 替换：删除所有相似记忆，添加新记忆
                        conflicts_detected.append({"action": "replace"})

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
                    # 无相似记忆，直接添加
                    await self.storage.add(item)
                    actually_added += 1
                    logger.info(f"  无相似记忆，直接存储")
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

        prompt = f"""从以下对话中提取重要的记忆事实。

对话：
{json.dumps(messages, ensure_ascii=False, indent=2)}

要求：
1. 提取用户偏好、重要事件、关键信息
2. 每条记忆应该简洁明确
3. 过滤掉无关紧要的寒暄和礼貌用语

请返回 JSON 格式：
{{
    "memories": [
        {{
            "content": "记忆内容",
            "type": "fact/preference/event/context",
            "entities": ["实体1", "实体2"],
            "keywords": ["关键词1", "关键词2"]
        }}
    ]
}}

类型说明：
- fact: 事实信息（如：姓名、职业、年龄）
- preference: 用户偏好（如：喜欢、不喜欢、习惯）
- event: 发生的事件（如：搬家、换工作）
- context: 对话背景（如：当前情境、环境信息）
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

                memory = MemoryItem(
                    id=str(uuid.uuid4()),
                    content=item["content"],
                    memory_type=memory_type,
                    user_id=user_id,
                    session_id=session_id,
                    entities=item.get("entities", []),
                    keywords=item.get("keywords", []),
                )
                memories.append(memory)

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
