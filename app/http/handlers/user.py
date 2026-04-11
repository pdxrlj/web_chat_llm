from app.http.handlers.base import router
from app.http.response import NlResponse
from fastapi import Request
from pydantic import BaseModel, Field
from core.model.user_repo import check_user_exists, check_user_password, create_user
from pydantic import field_validator


class LoginRequest(BaseModel):
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")

    @field_validator("username")
    @classmethod
    def username_must_be_alphanumeric(cls, v):
        if not v.isalnum():
            raise ValueError("用户名必须是字母或数字")
        return v

    @field_validator("password")
    @classmethod
    def password_must_be_alphanumeric(cls, v):
        if not v.isalnum():
            raise ValueError("密码必须是字母或数字")
        return v


@router.post("/v1/chat/login")
async def login(request: Request, login_req: LoginRequest):
    """
    用户登录

    Args:
        login_req: 登录请求体
            username: 用户名
            password: 密码

    Returns:
        NlResponse: 登录成功响应
    """

    # 检查用户名是否存在
    exists = await check_user_exists(login_req.username)
    if not exists:
        return NlResponse(content={}, message="用户名不存在")

    if exists:
        # 检查密码是否匹配
        password_match = await check_user_password(
            login_req.username, login_req.password
        )
        if not password_match:
            return NlResponse(content={}, message="密码错误")
        return NlResponse(content={}, message="登录成功")

    await create_user(login_req.username, login_req.password)
    return NlResponse(content={}, message="注册成功")
