from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.sql import func
from core.model.base import Base


class EmotionSpeculate(Base):
    """
    情感分析记录
    """

    __tablename__ = "emotion_speculate"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    session_id = Column(String, index=True)
    role = Column(String)
    query = Column(String)
    emotion = Column(JSON)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
