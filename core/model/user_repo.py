from sqlalchemy import select

from core.model.base import get_session
from core.model.user import UserModel, UserSessionModel


# ---------------------------------------------------------------------------
# session_id → user_id 简易内存缓存
# ---------------------------------------------------------------------------
_session_user_cache: dict[str, int] = {}


async def create_user(username: str, password: str) -> UserModel:
    """
    创建新用户。

    Args:
        username: 用户名
        password: 密码

    Returns:
        UserModel: 创建的用户对象
    """
    async for session in get_session():
        user = UserModel(username=username, password=password)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user
    raise RuntimeError("无法获取数据库会话")


async def get_user_by_session_id(session_id: str) -> int | None:
    """
    根据会话ID获取用户ID（带内存缓存）。

    Args:
        session_id: 会话ID

    Returns:
        int | None: 用户ID，不存在则返回 None
    """
    # 先查缓存
    cached = _session_user_cache.get(session_id)
    if cached is not None:
        return cached

    async for session in get_session():
        result = await session.execute(
            select(UserModel.id)
            .join(UserSessionModel, UserSessionModel.user_id == UserModel.id)
            .where(UserSessionModel.session_id == session_id)
        )
        user_id = result.scalar_one_or_none()
        if user_id is not None:
            _session_user_cache[session_id] = user_id
        return user_id
    raise RuntimeError("无法获取数据库会话")


async def get_username_by_session_id(session_id: str) -> str | None:
    """
    根据会话ID获取用户名。

    Args:
        session_id: 会话ID

    Returns:
        str | None: 用户名，不存在则返回 None
    """
    user_id = await get_user_by_session_id(session_id)
    if user_id is None:
        return None
    user = await get_user_by_id(user_id)
    return user.username if user else None


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


async def check_user_exists(username: str) -> bool:
    """
    检查用户名是否存在。

    Args:
        username: 用户名

    Returns:
        bool: 是否存在
    """
    async for session in get_session():
        result = await session.execute(
            select(UserModel).where(UserModel.username == username)
        )
        return result.scalar_one_or_none() is not None
    raise RuntimeError("无法获取数据库会话")


async def check_user_password(username: str, password: str) -> bool:
    """
    检查用户名和密码是否匹配。

    Args:
        username: 用户名
        password: 密码

    Returns:
        bool: 是否匹配
    """
    async for session in get_session():
        result = await session.execute(
            select(UserModel).where(UserModel.username == username)
        )
        user = result.scalar_one_or_none()
        if user:
            return user.password == password
        return False
    raise RuntimeError("无法获取数据库会话")


async def add_user_session_id(username: str, session_id: str) -> bool:
    """
    为用户新增一个会话ID（一个用户可以有多个会话）。

    Args:
        username: 用户名
        session_id: 新的会话ID

    Returns:
        bool: 是否添加成功
    """
    async for session in get_session():
        # 查找用户
        result = await session.execute(
            select(UserModel).where(UserModel.username == username)
        )
        user = result.scalar_one_or_none()
        if not user:
            return False

        # 检查该 session_id 是否已存在
        existing = await session.execute(
            select(UserSessionModel).where(UserSessionModel.session_id == session_id)
        )
        if existing.scalar_one_or_none():
            return False

        # 新增一条会话记录
        new_session = UserSessionModel(user_id=user.id, session_id=session_id)
        session.add(new_session)
        await session.commit()

        # 更新缓存
        _session_user_cache[session_id] = user.id
        return True
    raise RuntimeError("无法获取数据库会话")
