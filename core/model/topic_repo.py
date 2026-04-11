from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Result

from core.model.base import get_session
from core.model.topic import ChatTopicModel


async def save_chat_topic(
    *,
    session_id: str,
    username: str,
    title: str,
    description: str,
) -> ChatTopicModel | None:
    """
    保存或更新聊天话题。

    如果 (session_id, username) 组合已存在，则更新标题和描述；
    否则创建新记录。

    Args:
        session_id: 会话ID
        username: 用户名
        title: 标题
        description: 描述

    Returns:
        ChatTopicModel | None: 创建或更新的话题对象
    """
    async for session in get_session():
        stmt = (
            pg_insert(ChatTopicModel)
            .values(
                session_id=session_id,
                username=username,
                title=title,
                description=description,
            )
            .on_conflict_do_update(
                index_elements=[ChatTopicModel.session_id, ChatTopicModel.username],
                set_={
                    "title": title,
                    "description": description,
                    "updated_at": func.now(),
                },
            )
            .returning(ChatTopicModel)
        )
        result: Result[tuple[ChatTopicModel]] = await session.execute(stmt)
        await session.commit()
        return result.scalars().first()
    raise RuntimeError("无法获取数据库会话")


async def get_chat_topic(session_id: str, username: str) -> ChatTopicModel | None:
    """
    根据会话ID和用户名获取话题。

    Args:
        session_id: 会话ID
        username: 用户名

    Returns:
        ChatTopicModel | None: 话题对象，不存在则返回 None
    """
    from sqlalchemy import select

    async for session in get_session():
        result = await session.execute(
            select(ChatTopicModel).where(
                ChatTopicModel.session_id == session_id,
                ChatTopicModel.username == username,
            )
        )
        return result.scalar_one_or_none()
    raise RuntimeError("无法获取数据库会话")


async def get_chat_topics_by_session(
    session_id: str,
    page: int = 1,
    page_size: int = 20,
) -> list[ChatTopicModel]:
    """
    根据会话ID获取所有话题。

    Args:
        session_id: 会话ID
        page: 页码
        page_size: 每页数量

    Returns:
        list[ChatTopicModel]: 话题列表
    """
    from sqlalchemy import select

    async for session in get_session():
        result = await session.execute(
            select(ChatTopicModel)
            .where(ChatTopicModel.session_id == session_id)
            .order_by(ChatTopicModel.created_at.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        return list(result.scalars().all())
    raise RuntimeError("无法获取数据库会话")


async def delete_chat_topic(session_id: str, username: str) -> bool:
    """
    删除话题。

    Args:
        session_id: 会话ID
        username: 用户名

    Returns:
        bool: 是否删除成功（总是返回 True）
    """
    from sqlalchemy import delete

    async for session in get_session():
        _ = await session.execute(
            delete(ChatTopicModel).where(
                ChatTopicModel.session_id == session_id,
                ChatTopicModel.username == username,
            )
        )
        await session.commit()
        return True
    raise RuntimeError("无法获取数据库会话")
