"""智能数据处理器"""

import json
import logging
from openai import AsyncOpenAI
from pydantic import SecretStr

from .models import DataRecord, ProcessingAction, ProcessingResult, ProcessingDecision
from core.config import config

logger = logging.getLogger(__name__)


class IntelligentDataProcessor:
    """智能数据处理器
    
    使用 LLM 自动分析数据记录，决定合并、删除、新增或跳过操作。
    
    示例：
        processor = IntelligentDataProcessor()
        
        # 处理新数据
        new_record = DataRecord(
            id="new_001",
            content="用户不喜欢颜文字",
            record_type="preference"
        )
        
        existing_records = [
            DataRecord(id="old_001", content="用户喜欢吃葡萄", record_type="preference"),
            DataRecord(id="old_002", content="用户喜欢菠萝派", record_type="preference")
        ]
        
        result = await processor.process(new_record, existing_records)
        print(f"动作: {result.action}, 理由: {result.reason}")
    """
    
    def __init__(self, llm_name: str = "memory"):
        """
        初始化处理器
        
        Args:
            llm_name: 配置文件中的 LLM 名称
        """
        llm_config = config.get_llm(llm_name)
        if not llm_config:
            raise ValueError(f"未找到 LLM 配置: {llm_name}")
        
        self.llm_model = llm_config.model
        
        # 构建 OpenAI 客户端
        client_kwargs = {}
        if llm_config.base_url:
            client_kwargs["base_url"] = llm_config.base_url
        if llm_config.api_key:
            # 处理 api_key 可能是 SecretStr 的情况
            api_key = llm_config.api_key
            if isinstance(api_key, SecretStr):
                api_key = api_key.get_secret_value()
            client_kwargs["api_key"] = api_key
        
        self.llm_client = AsyncOpenAI(**client_kwargs)
    
    async def process(
        self,
        new_record: DataRecord,
        existing_records: list[DataRecord],
        similarity_threshold: float = 0.7,
    ) -> ProcessingResult:
        """
        处理新数据记录
        
        Args:
            new_record: 新数据记录
            existing_records: 已存在的记录列表
            similarity_threshold: 相似度阈值（用于预筛选）
        
        Returns:
            ProcessingResult: 处理结果
        """
        logger.info(f"处理新记录: {new_record.id} - {new_record.content[:50]}...")
        
        # 1. 检查是否有现有记录
        if not existing_records:
            logger.info("无现有记录，执行新增操作")
            return ProcessingResult(
                action=ProcessingAction.CREATE,
                new_record=new_record,
                reason="无相关现有记录，直接新增",
                confidence=1.0
            )
        
        # 2. 筛选相似记录（简单关键词匹配，可扩展为向量相似度）
        similar_records = self._find_similar_records(
            new_record, 
            existing_records,
            similarity_threshold
        )
        
        if not similar_records:
            logger.info("无相似记录，执行新增操作")
            return ProcessingResult(
                action=ProcessingAction.CREATE,
                new_record=new_record,
                reason="无相似的现有记录，直接新增",
                confidence=1.0
            )
        
        # 3. 使用 LLM 决策如何处理
        decision = await self._make_decision_with_llm(new_record, similar_records)
        
        logger.info(f"LLM 决策: {decision.action.value} - {decision.reason}")
        
        # 4. 构建处理结果
        return self._build_processing_result(new_record, similar_records, decision)
    
    def _find_similar_records(
        self,
        new_record: DataRecord,
        existing_records: list[DataRecord],
        threshold: float,
    ) -> list[DataRecord]:
        """
        查找相似记录（简单实现，可扩展为向量相似度）
        
        Args:
            new_record: 新记录
            existing_records: 现有记录列表
            threshold: 相似度阈值
        
        Returns:
            相似记录列表
        """
        # 简单关键词匹配（实际应用中应使用向量相似度）
        new_keywords = set(new_record.content.lower().split())
        similar = []
        
        for record in existing_records:
            existing_keywords = set(record.content.lower().split())
            # Jaccard 相似度
            intersection = new_keywords & existing_keywords
            union = new_keywords | existing_keywords
            similarity = len(intersection) / len(union) if union else 0
            
            if similarity >= threshold:
                similar.append(record)
                logger.debug(
                    f"相似记录: {record.id} (相似度: {similarity:.2f}) - {record.content[:30]}..."
                )
        
        return similar
    
    async def _make_decision_with_llm(
        self,
        new_record: DataRecord,
        similar_records: list[DataRecord],
        similarity_scores: list | None = None,  # [(record, score), ...]
    ) -> ProcessingDecision:
        """
        使用 LLM 做出处理决策（LLM 是唯一决策者）
        
        简化方案：不再做任何规则预筛选（向量阈值/实体匹配/Jaccard等），
        直接把候选记录全部交给 LLM，让模型根据语义自行判断操作类型。
        
        Args:
            new_record: 新记录
            similar_records: 相似记录列表
            similarity_scores: (可选) 每条记录的向量相似度分数
        
        Returns:
            ProcessingDecision: 决策结果
        """
        # 构建提示词（包含相似度分数作为参考信息）
        if similarity_scores:
            similar_list = "\n".join([
                f"[{i+1}] ID: {r.id}, 相似度: {score:.2%}, 类型: {r.record_type}, 内容: {r.content}"
                for i, (r, score) in enumerate(similarity_scores)
            ])
        else:
            similar_list = "\n".join([
                f"[{i+1}] ID: {r.id}, 类型: {r.record_type}, 内容: {r.content}"
                for i, r in enumerate(similar_records)
            ])

        # 构建相似度摘要
        if similarity_scores:
            scores_str = ", ".join([f"{score:.2f}" for _, score in similarity_scores])
            sim_info = f"\n【相似度参考】各记录与 new_record 的余弦相似度分别为: [{scores_str}]\n注意：语义冲突的内容（如'喜欢'vs'不喜欢'）可能相似度较低，不要仅凭相似度做判断！"
        else:
            sim_info = ""
        
        prompt = f"""你是用户记忆系统的智能分析引擎。你的任务是**唯一且最终**的决策者。

## 你的任务
分析新记录与现有记录的关系，判断应该执行什么操作。没有其他预筛选规则，
你拥有完全的决策权。

## 输入数据

### 新记录（待处理）
- 内容: {new_record.content}
- 类型: {new_record.record_type}
- 标签: {', '.join(new_record.tags) if new_record.tags else '无'}

### 已有相关记录（从向量搜索中找到的候选）
{similar_list}
{sim_info}

## 可选操作及判断依据

| 操作 | 含义 | 何时选择 |
|------|------|----------|
| **create** | 新增这条记录 | 主题不同、或补充了全新信息、或无法确定关系 |
| **delete** | 删除旧记录 + 新增本记录 | 新记录**明确否定/推翻**旧记录 |
| **merge** | 合并为一条更完整的记录 | 新旧记录**主题一致、信息互补、不矛盾** |
| **skip** | 跳过不处理 | 新记录完全重复、无价值、或信息已被覆盖 |

## 核心判断原则

1. **冲突检测是核心能力**：
   - "喜欢苹果" → "不喜欢苹果" → **delete** 旧的"喜欢苹果"
   - "住在上海" → "搬到北京了" → **delete** 旧的"住在上海"
   - "每天跑步" → "最近太忙没跑了" → **merge** 为"以前每天跑步，最近太忙没跑"
   
2. **情感词反转 = 冲突**：
   - 中文中的"喜欢/不喜欢"、"爱/讨厌"、"想/不想"等情感词反转意味着用户偏好改变
   - 即使两句话整体结构不同，只要涉及同一事物+情感相反，就是冲突
   
3. **相似度仅供参考**：
   - 高相似度(>0.85)通常意味着相关，但也可能是重复
   - **低相似度不代表无关**！"喜欢苹果"和"不喜欢苹果"的向量距离可能很远，但它们恰恰是最需要处理的冲突
   - 不要因为相似度低就自动判定为 create
   
4. **宁可多保留，不错删**：
   - 如果确实无法判断，选 create
   - 只有在明确识别到冲突时才 delete

## 输出格式

返回严格 JSON：
```json
{{
    "action": "create|delete|merge|skip",
    "reason": "一句话说明理由",
    "merged_content": "合并后的完整内容（仅merge操作需要）",
    "delete_ids": ["要删除的记录ID"],
    "confidence": 0.95
}}
```

## 示例

示例1 - 明确冲突：
新: "最近不喜欢吃苹果了，感觉太甜"
已有: [1] sim=72%, "很喜欢吃苹果，每天都要吃一个"
→ action="delete", reason="用户偏好从喜欢变为不喜欢", delete_ids=["id1"]

示例2 - 信息互补：
新: "喜欢葡萄，经常去超市买"
已有: [1] sim=88%, "喜欢吃葡萄"
→ action="merge", reason="新旧记录主题相同且互补", merged_content="喜欢吃葡萄，经常去超市买", delete_ids=["id1"]

示例3 - 完全无关：
新: "不喜欢颜文字"
已有: [1] sim=45%, "喜欢吃葡萄"
→ action="create", reason="主题完全不同（颜文字 vs 葡萄），独立保留"

示例4 - 重复：
新: "喜欢吃苹果"
已有: [1] sim=96%, "喜欢吃苹果"
→ action="skip", reason="内容几乎相同"

现在请分析以上数据并输出你的决策：
"""
        
        try:
            response = await self.llm_client.chat.completions.create(
                model=self.llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                response_format={"type": "json_object"},
                extra_body={"enable_thinking": False}
            )
            
            result_text = response.choices[0].message.content
            if not result_text:
                raise ValueError("LLM 返回空响应")
            
            result = json.loads(result_text)
            
            # 解析决策
            action_str = result.get("action", "create")
            try:
                action = ProcessingAction(action_str)
            except ValueError:
                action = ProcessingAction.CREATE
            
            # 解析 delete_ids（可能是索引或 ID）
            delete_ids_raw = result.get("delete_ids", [])
            delete_ids = []
            
            for item in delete_ids_raw:
                if isinstance(item, int):
                    # 如果是整数，当作索引处理（从1开始）
                    if 1 <= item <= len(similar_records):
                        delete_ids.append(similar_records[item - 1].id)
                        logger.debug(f"将索引 {item} 转换为 ID: {similar_records[item - 1].id}")
                elif isinstance(item, str):
                    # 如果是字符串，直接当作 ID
                    delete_ids.append(item)
            
            return ProcessingDecision(
                action=action,
                reason=result.get("reason", ""),
                merged_content=result.get("merged_content"),
                delete_ids=delete_ids,
                confidence=result.get("confidence", 0.9)
            )
            
        except Exception as e:
            logger.error(f"LLM 决策失败: {e}")
            # 失败时默认新增
            return ProcessingDecision(
                action=ProcessingAction.CREATE,
                reason=f"LLM 决策失败，默认新增: {str(e)}",
                confidence=0.5
            )
    
    def _build_processing_result(
        self,
        new_record: DataRecord,
        similar_records: list[DataRecord],
        decision: ProcessingDecision,
    ) -> ProcessingResult:
        """
        构建处理结果
        
        Args:
            new_record: 新记录
            similar_records: 相似记录
            decision: 决策结果
        
        Returns:
            ProcessingResult: 处理结果
        """
        # 确定 affected_ids
        if decision.action == ProcessingAction.DELETE:
            # DELETE: 使用 LLM 指定的 delete_ids
            affected_ids = decision.delete_ids if decision.delete_ids else [r.id for r in similar_records]
        elif decision.action == ProcessingAction.MERGE:
            # MERGE: 使用 LLM 指定的 delete_ids 或所有相似记录
            affected_ids = decision.delete_ids if decision.delete_ids else [r.id for r in similar_records]
        else:
            # 其他操作：记录所有相似记录
            affected_ids = [r.id for r in similar_records]
        
        result = ProcessingResult(
            action=decision.action,
            reason=decision.reason,
            confidence=decision.confidence,
            affected_ids=affected_ids
        )
        
        if decision.action == ProcessingAction.MERGE:
            # 合并操作
            result.merged_content = decision.merged_content
            result.original_id = similar_records[0].id if similar_records else None
            result.conflict_detected = True
            result.conflict_type = "complementary"
            
        elif decision.action == ProcessingAction.DELETE:
            # 删除操作
            result.original_id = similar_records[0].id if similar_records else None
            result.conflict_detected = True
            result.conflict_type = "contradiction"
            
        elif decision.action == ProcessingAction.CREATE:
            # 新增操作
            result.new_record = new_record
            
        elif decision.action == ProcessingAction.SKIP:
            # 跳过操作
            result.original_id = similar_records[0].id if similar_records else None
        
        return result
