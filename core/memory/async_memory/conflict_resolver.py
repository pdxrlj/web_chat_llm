"""冲突解决器"""

import json
import logging
from enum import Enum
from typing import Optional, List

from openai import AsyncOpenAI

from .models import ConflictInfo, MemoryItem

logger = logging.getLogger(__name__)


class MemoryAction(Enum):
    """记忆处理动作"""
    REJECT = "reject"      # 拒绝新记忆（无价值）
    MERGE = "merge"        # 合并新旧记忆
    REPLACE = "replace"    # 替换旧记忆
    APPEND = "append"      # 直接添加新记忆


class ConflictResolver:
    """智能冲突解决器"""

    def __init__(
        self,
        openai_client: AsyncOpenAI,
        model: str = "gpt-4o-mini",
        temperature: float = 0.1,
        enable_thinking: bool = False,
    ):
        self.client = openai_client
        self.model = model
        self.temperature = temperature
        self.enable_thinking = enable_thinking

    async def evaluate_memory(
        self,
        new_memory: MemoryItem,
        similar_memories: List[tuple],  # List[(MemoryItem, similarity)]
    ) -> tuple[MemoryAction, Optional[str], Optional[List[str]]]:
        """评估新记忆如何处理

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
            return MemoryAction.APPEND, None, None

        # 构建 prompt
        similar_list = "\n".join([
            f"[{i+1}] (相似度:{sim:.4f}) {mem.content}"
            for i, (mem, sim) in enumerate(similar_memories)
        ])

        prompt = f"""你是一个记忆管理助手。请评估新记忆与已有相似记忆的关系。

【新记忆】
{new_memory.content}

【已有相似记忆】
{similar_list}

请判断应该如何处理，返回 JSON 格式：
{{
    "action": "merge/replace/append/reject",
    "reason": "判断理由",
    "merged_content": "合并后的内容（仅merge时需要）",
    "delete_ids": ["需要删除的记忆编号，如1,2,3"]
}}

判断标准：
- merge: 新旧记忆信息互补，合并后更完整
- replace: 新记忆完全覆盖或更新旧记忆
- append: 新记忆独立有价值，需要保留
- reject: 新记忆无新信息，可以丢弃

注意：编号对应【已有相似记忆】中的序号 [1], [2], [3] 等。
"""

        try:
            request_params = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": self.temperature,
                "response_format": {"type": "json_object"},
            }

            request_params["extra_body"] = {"enable_thinking": False}

            response = await self.client.chat.completions.create(**request_params)
            result = json.loads(response.choices[0].message.content)

            action_str = result.get("action", "append")
            reason = result.get("reason", "")
            merged_content = result.get("merged_content")
            delete_indices = result.get("delete_ids", [])

            logger.info(f"    LLM 判断: action={action_str}, reason={reason}")

            # 解析动作
            try:
                action = MemoryAction(action_str)
            except ValueError:
                action = MemoryAction.APPEND

            # 获取需要删除的记忆ID
            ids_to_delete = []
            for idx in delete_indices:
                if isinstance(idx, int) and 1 <= idx <= len(similar_memories):
                    ids_to_delete.append(similar_memories[idx - 1][0].id)

            return action, merged_content, ids_to_delete if ids_to_delete else None

        except Exception as e:
            logger.error(f"LLM 评估失败: {e}")
            return MemoryAction.APPEND, None, None

    async def detect_conflict(
        self,
        old_memory: MemoryItem,
        new_memory: MemoryItem,
        _similarity_threshold: float = 0.6,
        similarity_score: float = 0.0,
    ) -> Optional[ConflictInfo]:
        """检测两个记忆是否存在冲突或需要合并（兼容旧接口）"""

        # 使用新的评估方法
        action, _merged_content, _ids_to_delete = await self.evaluate_memory(
            new_memory, [(old_memory, similarity_score)]
        )

        if action == MemoryAction.MERGE:
            return ConflictInfo(
                old_memory=old_memory,
                new_memory=new_memory,
                conflict_type="update",
                similarity_score=similarity_score,
            )
        elif action == MemoryAction.REPLACE:
            return ConflictInfo(
                old_memory=old_memory,
                new_memory=new_memory,
                conflict_type="contradiction",
                similarity_score=similarity_score,
            )
        elif action == MemoryAction.REJECT:
            # 标记为重复，让调用方跳过
            return ConflictInfo(
                old_memory=old_memory,
                new_memory=new_memory,
                conflict_type="duplicate",
                similarity_score=similarity_score,
            )

        return None

