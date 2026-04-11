from fastapi import Header
from pydantic import BaseModel, Field
from app.http.response import NlResponse
from app.http.handlers.base import router
from core.model.topic_repo import get_chat_topics_by_session
from fastapi import Depends


class ChatTopicListRequest(BaseModel):
    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=20, ge=1, le=100, description="每页数量")


@router.post("/chat/user/topics/list")
async def topic(
    req: ChatTopicListRequest,
    session_id: str = Depends(Header(..., description="会话 ID")),
):
    """获取用户对话主题列表

    Args:
        req: 请求体（page, page_size）
        session_id: 从请求头获取的会话 ID

    Returns:
        NlResponse: 包含主题列表的响应
    """

    topic_list = await get_chat_topics_by_session(session_id, req.page, req.page_size)

    return NlResponse(
        content={
            "topics": topic_list,
        },
        message="success",
    )
