from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from core.model.base import Base


class UserModel(Base):
    __tablename__: str = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True, comment="用户名"
    )
    session_id: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True, comment="会话ID"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        comment="创建时间",
        insert_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        comment="更新时间",
        insert_default=func.now(),
        onupdate=func.now(),
    )
