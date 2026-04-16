from sqlalchemy import select, delete

from core.model.base import get_session
from core.model.chat_analyze import ChatAnalyze


async def add_chat_analyze(
    *,
    session_id: str,
    role: str,
    report: dict,
) -> ChatAnalyze:
    """
    添加聊天分析报告记录。

    Args:
        session_id: 会话ID
        role: 角色
        report: 分析报告结果（JSON）

    Returns:
        ChatAnalyze: 创建的分析报告记录对象
    """
    async for session in get_session():
        record = ChatAnalyze(
            session_id=session_id,
            role=role,
            report=report,
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record
    raise RuntimeError("无法获取数据库会话")


async def get_chat_analyze_by_id(record_id: int) -> ChatAnalyze | None:
    """
    根据ID获取聊天分析报告。

    Args:
        record_id: 记录ID

    Returns:
        ChatAnalyze | None: 分析报告记录，不存在则返回 None
    """
    async for session in get_session():
        result = await session.execute(
            select(ChatAnalyze).where(ChatAnalyze.id == record_id)
        )
        return result.scalar_one_or_none()
    raise RuntimeError("无法获取数据库会话")


async def get_chat_analyzes_by_session_id(
    *,
    session_id: str,
    page: int = 1,
    page_size: int = 50,
) -> list[ChatAnalyze]:
    """
    根据会话ID获取聊天分析报告列表。

    Args:
        session_id: 会话ID
        page: 页码
        page_size: 每页数量

    Returns:
        list[ChatAnalyze]: 分析报告列表
    """
    async for session in get_session():
        result = await session.execute(
            select(ChatAnalyze)
            .where(ChatAnalyze.session_id == session_id)
            .order_by(ChatAnalyze.created_at.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        return list(result.scalars().all())
    raise RuntimeError("无法获取数据库会话")


async def get_latest_chat_analyze_by_session_id(
    session_id: str,
) -> ChatAnalyze | None:
    """
    获取指定会话的最新一条分析报告。

    Args:
        session_id: 会话ID

    Returns:
        ChatAnalyze | None: 最新的分析报告，不存在则返回 None
    """
    async for session in get_session():
        result = await session.execute(
            select(ChatAnalyze)
            .where(ChatAnalyze.session_id == session_id)
            .order_by(ChatAnalyze.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
    raise RuntimeError("无法获取数据库会话")


async def delete_chat_analyze(record_id: int) -> bool:
    """
    删除单条聊天分析报告。

    Args:
        record_id: 记录ID

    Returns:
        bool: 是否删除成功
    """
    async for session in get_session():
        _ = await session.execute(
            delete(ChatAnalyze).where(ChatAnalyze.id == record_id)
        )
        await session.commit()
        return True
    raise RuntimeError("无法获取数据库会话")


async def delete_chat_analyzes_by_session_id(session_id: str) -> bool:
    """
    删除指定会话的所有聊天分析报告。

    Args:
        session_id: 会话ID

    Returns:
        bool: 是否删除成功
    """
    async for session in get_session():
        _ = await session.execute(
            delete(ChatAnalyze).where(ChatAnalyze.session_id == session_id)
        )
        await session.commit()
        return True
    raise RuntimeError("无法获取数据库会话")
