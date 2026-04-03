from datetime import datetime, timedelta, timezone

from sqlalchemy import DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from core.logger import setup_logger
from core.model.base import Base

logger = setup_logger(__name__)

UTC_8 = timezone(timedelta(hours=8))


class ChatTopicModel(Base):
    """聊天话题模型。"""

    __tablename__: str = "chat_topics"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True, comment="会话ID"
    )
    username: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True, comment="用户名"
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False, comment="标题")
    description: Mapped[str] = mapped_column(
        String(256), nullable=False, comment="描述"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        insert_default=func.now(),
        comment="创建时间",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        insert_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )

    __table_args__: tuple[UniqueConstraint] = (
        UniqueConstraint("session_id", "username", name="uq_chat_topic_session_user"),
    )
