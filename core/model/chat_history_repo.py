from sqlalchemy import select, delete

from core.model.base import get_session
from core.model.chat_history import ChatHistory


async def add_chat_history(
    *,
    session_id: str,
    role: str,
    query: str,
    answer: str,
) -> ChatHistory:
    """
    添加聊天记录。

    Args:
        session_id: 会话ID
        role: 角色
        query: 用户提问
        answer: 模型回答

    Returns:
        ChatHistory: 创建的聊天记录对象
    """
    async for session in get_session():
        record = ChatHistory(
            session_id=session_id,
            role=role,
            query=query,
            answer=answer,
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record
    raise RuntimeError("无法获取数据库会话")


async def get_chat_history_by_id(record_id: int) -> ChatHistory | None:
    """
    根据ID获取聊天记录。

    Args:
        record_id: 记录ID

    Returns:
        ChatHistory | None: 聊天记录对象，不存在则返回 None
    """
    async for session in get_session():
        result = await session.execute(
            select(ChatHistory).where(ChatHistory.id == record_id)
        )
        return result.scalar_one_or_none()
    raise RuntimeError("无法获取数据库会话")


async def get_chat_histories_by_session_id(
    *,
    session_id: str,
    page: int = 1,
    page_size: int = 50,
) -> list[ChatHistory]:
    """
    根据会话ID获取聊天记录列表。

    Args:
        session_id: 会话ID
        page: 页码
        page_size: 每页数量

    Returns:
        list[ChatHistory]: 聊天记录列表
    """
    async for session in get_session():
        result = await session.execute(
            select(ChatHistory)
            .where(ChatHistory.session_id == session_id)
            .order_by(ChatHistory.created_at.asc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        return list(result.scalars().all())
    raise RuntimeError("无法获取数据库会话")


async def delete_chat_history(record_id: int) -> bool:
    """
    删除单条聊天记录。

    Args:
        record_id: 记录ID

    Returns:
        bool: 是否删除成功
    """
    async for session in get_session():
        _ = await session.execute(
            delete(ChatHistory).where(ChatHistory.id == record_id)
        )
        await session.commit()
        return True
    raise RuntimeError("无法获取数据库会话")


async def delete_chat_histories_by_session_id(session_id: str) -> int:
    """
    删除指定会话的所有聊天记录。

    Args:
        session_id: 会话ID

    Returns:
        int: 删除的记录数
    """
    async for session in get_session():
        _ = await session.execute(
            delete(ChatHistory).where(ChatHistory.session_id == session_id)
        )
        await session.commit()
        return True
    raise RuntimeError("无法获取数据库会话")
