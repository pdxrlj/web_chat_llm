"""
历史聊天内容存储,pg
"""

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from core.model.base import Base


class ChatHistory(Base):
    """
    聊天历史记录
    """

    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    session_id = Column(String, index=True)
    role = Column(String)
    query = Column(String)
    answer = Column(String)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
