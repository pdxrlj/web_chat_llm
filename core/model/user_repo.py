from sqlalchemy import select

from core.model.base import get_session
from core.model.user import UserModel


async def create_user(username: str, session_id: str) -> UserModel:
    """
    创建新用户。

    Args:
        username: 用户名
        session_id: 会话ID

    Returns:
        UserModel: 创建的用户对象
    """
    async for session in get_session():
        user = UserModel(username=username, session_id=session_id)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user
    raise RuntimeError("无法获取数据库会话")


async def get_user_by_session_id(session_id: str) -> UserModel | None:
    """
    根据会话ID获取用户。

    Args:
        session_id: 会话ID

    Returns:
        UserModel | None: 用户对象，不存在则返回 None
    """
    async for session in get_session():
        result = await session.execute(
            select(UserModel).where(UserModel.session_id == session_id)
        )
        return result.scalar_one_or_none()
    raise RuntimeError("无法获取数据库会话")


async def get_user_by_id(user_id: int) -> UserModel | None:
    """
    根据用户ID获取用户。

    Args:
        user_id: 用户ID

    Returns:
        UserModel | None: 用户对象，不存在则返回 None
    """
    async for session in get_session():
        result = await session.execute(select(UserModel).where(UserModel.id == user_id))
        return result.scalar_one_or_none()
    raise RuntimeError("无法获取数据库会话")


async def delete_user(user_id: int) -> bool:
    """
    删除用户。

    Args:
        user_id: 用户ID

    Returns:
        bool: 是否删除成功
    """
    async for session in get_session():
        user = await session.get(UserModel, user_id)
        if user:
            await session.delete(user)
            await session.commit()
            return True
        return False
    raise RuntimeError("无法获取数据库会话")
