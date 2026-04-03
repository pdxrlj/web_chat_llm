"""数据模型定义"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class ConflictResolution(Enum):
    """冲突解决策略"""
    REPLACE = "replace"  # 新数据替换旧数据
    MERGE = "merge"  # 智能合并
    KEEP_OLD = "keep_old"  # 保留旧数据
    KEEP_BOTH = "keep_both"  # 保留两者


class MemoryType(Enum):
    """记忆类型"""
    FACT = "fact"  # 事实性记忆（如用户偏好）
    EVENT = "event"  # 事件性记忆（如发生了什么）
    CONTEXT = "context"  # 上下文记忆（如对话背景）


@dataclass
class MemoryItem:
    """记忆项数据结构"""
    id: str
    content: str  # 记忆内容
    embedding: Optional[List[float]] = None  # 向量嵌入
    memory_type: MemoryType = MemoryType.FACT
    
    # 元数据
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # 语义信息
    entities: List[str] = field(default_factory=list)  # 提取的实体
    keywords: List[str] = field(default_factory=list)  # 关键词
    
    # 冲突处理
    version: int = 1
    is_active: bool = True
    superseded_by: Optional[str] = None  # 被哪个记忆替代
    
    # 自定义元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "content": self.content,
            "memory_type": self.memory_type.value,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "entities": self.entities,
            "keywords": self.keywords,
            "version": self.version,
            "is_active": self.is_active,
            "superseded_by": self.superseded_by,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryItem":
        """从字典创建"""
        return cls(
            id=data["id"],
            content=data["content"],
            memory_type=MemoryType(data.get("memory_type", "fact")),
            user_id=data.get("user_id"),
            session_id=data.get("session_id"),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            entities=data.get("entities", []),
            keywords=data.get("keywords", []),
            version=data.get("version", 1),
            is_active=data.get("is_active", True),
            superseded_by=data.get("superseded_by"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ConflictInfo:
    """冲突信息"""
    old_memory: MemoryItem
    new_memory: MemoryItem
    conflict_type: str  # "contradiction" | "update" | "duplicate"
    similarity_score: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "old_memory": self.old_memory.to_dict(),
            "new_memory": self.new_memory.to_dict(),
            "conflict_type": self.conflict_type,
            "similarity_score": self.similarity_score,
        }
