"""记忆冲突解决器 - 基于 IntelligentDataProcessor"""

import logging
from typing import Optional, List

from openai import AsyncOpenAI

from .models import ConflictInfo, MemoryItem
from ..data_processor import IntelligentDataProcessor, DataRecord, ProcessingAction

logger = logging.getLogger(__name__)


class MemoryAction:
    """记忆处理动作（映射到 ProcessingAction）"""
    REJECT = ProcessingAction.SKIP      # 拒绝新记忆（无价值）
    MERGE = ProcessingAction.MERGE      # 合并新旧记忆
    REPLACE = ProcessingAction.DELETE   # 替换旧记忆
    APPEND = ProcessingAction.CREATE    # 直接添加新记忆


class ConflictResolver:
    """智能冲突解决器 - 基于 IntelligentDataProcessor"""

    def __init__(
        self,
        openai_client: AsyncOpenAI,
        model: str = "gpt-4o-mini",
        temperature: float = 0.1,
        enable_thinking: bool = False,
    ):
        """
        初始化冲突解决器
        
        Args:
            openai_client: OpenAI 客户端
            model: 模型名称
            temperature: 温度参数
            enable_thinking: 是否启用思考模式（暂不支持）
        """
        self.client = openai_client
        self.model = model
        self.temperature = temperature
        self.enable_thinking = enable_thinking
        
        # 使用 IntelligentDataProcessor 作为核心处理器
        self.processor = IntelligentDataProcessor.__new__(IntelligentDataProcessor)
        # 直接注入 client（避免重复创建）
        self.processor.llm_client = openai_client
        self.processor.llm_model = model

    @staticmethod
    def _memory_to_record(memory: MemoryItem) -> DataRecord:
        """将 MemoryItem 转换为 DataRecord"""
        return DataRecord(
            id=memory.id,
            content=memory.content,
            record_type=memory.memory_type.value,
            metadata={
                "user_id": memory.user_id,
                "session_id": memory.session_id,
                "entities": memory.entities,
                "keywords": memory.keywords,
                **memory.metadata
            },
            tags=memory.keywords,
            created_at=memory.created_at,
            updated_at=memory.updated_at,
        )

    @staticmethod
    def _record_to_memory(record: DataRecord, memory_template: MemoryItem) -> MemoryItem:
        """将 DataRecord 转换为 MemoryItem（保留原始元数据）"""
        from ..async_memory.models import MemoryType
        
        return MemoryItem(
            id=record.id,
            content=record.content,
            memory_type=MemoryType(record.record_type),
            user_id=memory_template.user_id,
            session_id=memory_template.session_id,
            embedding=memory_template.embedding,
            entities=record.metadata.get("entities", []),
            keywords=record.tags,
            metadata=record.metadata,
        )

    async def evaluate_memory(
        self,
        new_memory: MemoryItem,
        similar_memories: List[tuple],  # List[(MemoryItem, similarity)]
    ) -> tuple[ProcessingAction, Optional[str], Optional[List[str]]]:
        """
        评估新记忆如何处理
        
        Args:
            new_memory: 新记忆
            similar_memories: 相似记忆列表 [(MemoryItem, similarity), ...]
            
        Returns:
            (action, merged_content, ids_to_delete)
            - action: 处理动作
            - merged_content: 合并后的内容（MERGE时有效）
            - ids_to_delete: 需要删除的记忆ID列表
        """
        if not similar_memories:
            logger.info(f"    无相似记忆，直接添加")
            return ProcessingAction.CREATE, None, None

        # 转换为 DataRecord
        new_record = self._memory_to_record(new_memory)
        similar_records = [
            (self._memory_to_record(mem), sim) 
            for mem, sim in similar_memories
        ]

        # 提取相似记录列表（不含相似度分数）
        existing_records = [record for record, _ in similar_records]

        # 直接调用 LLM 决策（简化方案：去掉所有预筛选，LLM是唯一决策者）
        # memory.py 已简化为只做向量搜索取 top_k，不再做规则过滤
        from ..data_processor import ProcessingDecision

        # 构建 (DataRecord, similarity_score) 列表传给 LLM
        records_with_scores = list(zip(existing_records, [sim for _, sim in similar_memories]))

        decision = await self.processor._make_decision_with_llm(
            new_record, existing_records, similarity_scores=records_with_scores
        )

        # 构建结果（复用 processor 的 _build_processing_result 逻辑）
        result = self.processor._build_processing_result(new_record, existing_records, decision)

        logger.info(f"    LLM 判断: action={result.action.value}, reason={result.reason}")

        # 映射处理结果
        action = result.action
        merged_content = result.merged_content
        ids_to_delete = result.affected_ids if action in [ProcessingAction.MERGE, ProcessingAction.DELETE] else None

        return action, merged_content, ids_to_delete

    async def detect_conflict(
        self,
        old_memory: MemoryItem,
        new_memory: MemoryItem,
        _similarity_threshold: float = 0.6,
        similarity_score: float = 0.0,
    ) -> Optional[ConflictInfo]:
        """
        检测两个记忆是否存在冲突或需要合并（兼容旧接口）
        
        Args:
            old_memory: 旧记忆
            new_memory: 新记忆
            _similarity_threshold: 相似度阈值（暂未使用）
            similarity_score: 相似度分数
            
        Returns:
            ConflictInfo 或 None
        """
        # 使用新的评估方法
        action, _merged_content, _ids_to_delete = await self.evaluate_memory(
            new_memory, [(old_memory, similarity_score)]
        )

        if action == ProcessingAction.MERGE:
            return ConflictInfo(
                old_memory=old_memory,
                new_memory=new_memory,
                conflict_type="update",
                similarity_score=similarity_score,
            )
        elif action == ProcessingAction.DELETE:
            return ConflictInfo(
                old_memory=old_memory,
                new_memory=new_memory,
                conflict_type="contradiction",
                similarity_score=similarity_score,
            )
        elif action == ProcessingAction.SKIP:
            # 标记为重复，让调用方跳过
            return ConflictInfo(
                old_memory=old_memory,
                new_memory=new_memory,
                conflict_type="duplicate",
                similarity_score=similarity_score,
            )

        return None
