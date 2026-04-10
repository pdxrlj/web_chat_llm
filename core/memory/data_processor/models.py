"""数据处理模型定义"""

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class ProcessingAction(Enum):
    """数据处理动作"""
    MERGE = "merge"          # 合并：新旧数据信息互补
    DELETE = "delete"        # 删除：数据冲突或无效
    CREATE = "create"        # 新增：独立的新数据
    SKIP = "skip"            # 跳过：无价值或重复


class DataRecord(BaseModel):
    """数据记录模型"""
    
    id: str = Field(description="记录唯一标识")
    content: str = Field(description="文本内容")
    record_type: str = Field(default="general", description="记录类型（如：preference, fact, event）")
    metadata: dict[str, Any] = Field(default_factory=dict, description="元数据")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")
    
    # 可选字段
    tags: list[str] = Field(default_factory=list, description="标签")
    priority: int = Field(default=0, description="优先级（数字越大优先级越高）")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="置信度")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "user_001",
                "content": "用户喜欢菠萝派",
                "record_type": "preference",
                "metadata": {"source": "chat", "user_id": "pdx"},
                "tags": ["food", "preference"],
                "priority": 5,
                "confidence": 0.95
            }
        }


class ProcessingResult(BaseModel):
    """处理结果模型"""
    
    action: ProcessingAction = Field(description="执行的动作")
    original_id: Optional[str] = Field(default=None, description="原始记录ID（合并/删除时）")
    new_record: Optional[DataRecord] = Field(default=None, description="新记录（合并/新增时）")
    merged_content: Optional[str] = Field(default=None, description="合并后的内容")
    reason: str = Field(description="决策理由")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="决策置信度")
    
    # 冲突信息
    conflict_detected: bool = Field(default=False, description="是否检测到冲突")
    conflict_type: Optional[str] = Field(default=None, description="冲突类型")
    affected_ids: list[str] = Field(default_factory=list, description="受影响的记录ID列表")


class ProcessingDecision(BaseModel):
    """LLM 决策结果"""
    
    action: ProcessingAction = Field(description="处理动作")
    reason: str = Field(description="决策理由")
    merged_content: Optional[str] = Field(default=None, description="合并后的内容")
    delete_ids: list[str] = Field(default_factory=list, description="需要删除的记录ID")
    confidence: float = Field(default=0.9, description="决策置信度")
