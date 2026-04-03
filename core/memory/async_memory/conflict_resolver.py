"""冲突解决器"""

import json
import logging
from typing import Optional

from openai import AsyncOpenAI

from .models import ConflictInfo, ConflictResolution, MemoryItem

logger = logging.getLogger(__name__)


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

    async def detect_conflict(
        self,
        old_memory: MemoryItem,
        new_memory: MemoryItem,
        _similarity_threshold: float = 0.85,
    ) -> Optional[ConflictInfo]:
        """检测两个记忆是否存在冲突"""

        # 相同实体但内容不同 = 潜在冲突
        if old_memory.entities and new_memory.entities:
            common_entities = set(old_memory.entities) & set(new_memory.entities)
            if not common_entities:
                return None

        # 使用 LLM 判断冲突类型
        prompt = f"""分析以下两段记忆是否存在冲突，并判断冲突类型：

旧记忆：{old_memory.content}
新记忆：{new_memory.content}

请回答 JSON 格式：
{{
    "has_conflict": true/false,
    "conflict_type": "contradiction（矛盾）/ update（更新）/ duplicate（重复）/ none",
    "reason": "原因说明",
    "should_merge": true/false,
    "merged_content": "合并后的内容（如果需要合并）"
}}
"""

        try:
            # 构建请求参数
            request_params = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": self.temperature,
                "response_format": {"type": "json_object"},
            }

            # 添加 Qwen 的 extra_body 参数
            if self.enable_thinking:
                request_params["extra_body"] = {"enable_thinking": True}

            response = await self.client.chat.completions.create(**request_params)

            result = json.loads(response.choices[0].message.content)

            if not result.get("has_conflict"):
                return None

            conflict_type = result.get("conflict_type", "none")
            if conflict_type == "none":
                return None

            return ConflictInfo(
                old_memory=old_memory,
                new_memory=new_memory,
                conflict_type=conflict_type,
                similarity_score=0.0,
            )

        except Exception as e:
            logger.error(f"冲突检测失败: {e}")
            return None

    async def resolve_conflict(
        self,
        conflict: ConflictInfo,
        strategy: ConflictResolution = ConflictResolution.MERGE,
    ) -> MemoryItem:
        """解决冲突，返回最终记忆"""

        if strategy == ConflictResolution.REPLACE:
            # 直接替换
            conflict.new_memory.version = conflict.old_memory.version + 1
            conflict.new_memory.superseded_by = conflict.old_memory.id
            return conflict.new_memory

        elif strategy == ConflictResolution.KEEP_OLD:
            # 保留旧记忆
            return conflict.old_memory

        elif strategy == ConflictResolution.KEEP_BOTH:
            # 保留两者，标记为不同版本
            conflict.new_memory.version = conflict.old_memory.version + 1
            conflict.new_memory.metadata["parallel_version_of"] = conflict.old_memory.id
            return conflict.new_memory

        elif strategy == ConflictResolution.MERGE:
            # 智能合并
            merged_content = await self._merge_memories(conflict)

            # 创建合并后的记忆
            merged_memory = MemoryItem(
                id=conflict.new_memory.id,  # 使用新记忆 ID
                content=merged_content,
                memory_type=conflict.old_memory.memory_type,
                user_id=conflict.old_memory.user_id,
                entities=list(
                    set(conflict.old_memory.entities + conflict.new_memory.entities)
                ),
                keywords=list(
                    set(conflict.old_memory.keywords + conflict.new_memory.keywords)
                ),
                version=conflict.old_memory.version + 1,
                metadata={
                    **conflict.old_memory.metadata,
                    **conflict.new_memory.metadata,
                    "merged_from": [conflict.old_memory.id],
                },
            )

            return merged_memory

    async def _merge_memories(self, conflict: ConflictInfo) -> str:
        """使用 LLM 合并两个记忆"""

        prompt = f"""合并以下两段记忆，保留所有有效信息，解决矛盾：

旧记忆：{conflict.old_memory.content}
新记忆：{conflict.new_memory.content}
冲突类型：{conflict.conflict_type}

要求：
1. 如果是时间线更新（如用户偏好改变），保留最新信息
2. 如果是矛盾信息，用"之前...现在..."的方式表述
3. 如果是补充信息，合并为完整描述

请直接返回合并后的内容（不要解释）："""

        try:
            # 构建请求参数
            request_params = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": self.temperature,
            }

            # 添加 Qwen 的 extra_body 参数
            if self.enable_thinking:
                request_params["extra_body"] = {"enable_thinking": True}

            response = await self.client.chat.completions.create(**request_params)

            return response.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"合并记忆失败: {e}")
            # 失败时返回新记忆
            return conflict.new_memory.content
