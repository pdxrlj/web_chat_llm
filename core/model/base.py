from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类。"""

    pass


_engine: AsyncEngine | None = None
_async_session: async_sessionmaker[AsyncSession] | None = None


def conn(conn_str: str):
    """
    初始化数据库连接池和会话工厂。

    Args:
        conn_str: 数据库连接字符串，格式为：
            postgresql+asyncpg://user:password@host:port/database

    说明：
        - pool_size: 连接池大小，默认20个连接
        - max_overflow: 超出pool_size后允许的最大额外连接数，默认10个
        - pool_pre_ping: 每次使用连接前检测连接是否有效
        - pool_recycle: 连接回收时间（秒），默认3600秒（1小时）
        - echo: 是否打印SQL语句，生产环境建议关闭
    """
    global _engine, _async_session
    if _engine is None:
        _engine = create_async_engine(
            url=conn_str,
            echo=True,
            pool_size=20,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
        _async_session = async_sessionmaker(
            _engine, class_=AsyncSession, expire_on_commit=False
        )


async def migrate() -> None:
    """
    执行数据库迁移，创建所有表结构。

    注意：此函数为异步函数，需要使用 await 调用。
    """
    if _engine is None:
        raise RuntimeError("数据库连接未初始化，请先调用 conn() 函数")

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close():
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    获取数据库会话的异步生成器。

    用于 FastAPI 依赖注入，自动管理会话的生命周期。

    Yields:
        AsyncSession: 数据库会话实例

    Raises:
        RuntimeError: 数据库连接未初始化

    Example:
        ```python
        from fastapi import Depends
        from sqlalchemy.ext.asyncio import AsyncSession

        @router.get("/users")
        async def get_users(session: AsyncSession = Depends(get_session)):
            ...
        ```
    """
    if _async_session is None:
        raise RuntimeError("数据库连接未初始化，请先调用 conn() 函数")
    async with _async_session() as session:
        yield session
