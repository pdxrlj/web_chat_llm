import uuid

from pydantic import BaseModel, Field, field_validator

from app.http.handlers.base import router
from app.http.response import NlResponse
from core.model.user_repo import add_user_session_id, check_user_exists, create_user


class CreateSessionRequest(BaseModel):
    """创建会话请求。"""

    username: str = Field(..., description="用户名")

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if len(v) < 1:
            raise ValueError("用户名不能为空")
        if len(v) > 50:
            raise ValueError("用户名长度不能超过50个字符")
        return v


class NLARegisterResponse(BaseModel):
    """注册响应数据。"""

    username: str
    session_id: str


@router.post("/chat/session/create")
async def create_session(request: CreateSessionRequest) -> NlResponse:
    """
    创建新会话。

    为用户创建一个新的会话,返回会话ID。

    Args:
        request: 包含用户名的请求体

    Returns:
        NlResponse: 包含用户名和会话ID的响应
    """
    username = request.username
    session_id = str(uuid.uuid4())

    # 如果用户不存在则创建，然后添加会话
    if not await check_user_exists(username):
        return NlResponse(
            content={
                "username": username,
                "session_id": session_id,
            },
            status_code=404,
            message="用户不存在",
        )
    await add_user_session_id(username=username, session_id=session_id)

    return NlResponse(
        content=NLARegisterResponse(
            username=username, session_id=session_id
        ).model_dump(),
        message="success",
    )
