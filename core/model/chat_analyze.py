from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.sql import func
from core.model.base import Base


class ChatAnalyze(Base):
    """
    聊天记录分析报告
    """

    __tablename__ = "chat_analyze"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    session_id = Column(String, index=True)
    role = Column(String)
    report = Column(JSON)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
