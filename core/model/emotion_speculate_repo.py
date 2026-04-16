from sqlalchemy import select, delete

from core.model.base import get_session
from core.model.emotion_speculate import EmotionSpeculate


async def add_emotion_speculate(
    *,
    session_id: str,
    role: str,
    query: str,
    emotion: dict,
) -> EmotionSpeculate:
    """
    添加情感分析记录。

    Args:
        session_id: 会话ID
        role: 角色
        query: 触发分析的用户问题
        emotion: 情感分析结果（JSON）

    Returns:
        EmotionSpeculate: 创建的情感分析记录对象
    """
    async for session in get_session():
        record = EmotionSpeculate(
            session_id=session_id,
            role=role,
            query=query,
            emotion=emotion,
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record
    raise RuntimeError("无法获取数据库会话")


async def get_emotion_speculate_by_id(record_id: int) -> EmotionSpeculate | None:
    """
    根据ID获取情感分析记录。

    Args:
        record_id: 记录ID

    Returns:
        EmotionSpeculate | None: 情感分析记录对象，不存在则返回 None
    """
    async for session in get_session():
        result = await session.execute(
            select(EmotionSpeculate).where(EmotionSpeculate.id == record_id)
        )
        return result.scalar_one_or_none()
    raise RuntimeError("无法获取数据库会话")


async def get_emotion_speculates_by_session_id(
    *,
    session_id: str,
    page: int = 1,
    page_size: int = 50,
) -> list[EmotionSpeculate]:
    """
    根据会话ID获取情感分析记录列表。

    Args:
        session_id: 会话ID
        page: 页码
        page_size: 每页数量

    Returns:
        list[EmotionSpeculate]: 情感分析记录列表
    """
    async for session in get_session():
        result = await session.execute(
            select(EmotionSpeculate)
            .where(EmotionSpeculate.session_id == session_id)
            .order_by(EmotionSpeculate.created_at.asc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        return list(result.scalars().all())
    raise RuntimeError("无法获取数据库会话")


async def delete_emotion_speculate(record_id: int) -> bool:
    """
    删除单条情感分析记录。

    Args:
        record_id: 记录ID

    Returns:
        bool: 是否删除成功
    """
    async for session in get_session():
        _ = await session.execute(
            delete(EmotionSpeculate).where(EmotionSpeculate.id == record_id)
        )
        await session.commit()
        return True
    raise RuntimeError("无法获取数据库会话")


async def delete_emotion_speculates_by_session_id(session_id: str) -> bool:
    """
    删除指定会话的所有情感分析记录。

    Args:
        session_id: 会话ID

    Returns:
        bool: 是否删除成功
    """
    async for session in get_session():
        _ = await session.execute(
            delete(EmotionSpeculate).where(EmotionSpeculate.session_id == session_id)
        )
        await session.commit()
        return True
    raise RuntimeError("无法获取数据库会话")
