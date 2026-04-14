from fastapi import Header, Query
from app.http.response import NlResponse
from app.http.handlers.base import router
from core.model.topic_repo import get_chat_topics_by_username


@router.get("/chat/user/topics/list")
async def topic(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    username: str = Query(..., alias="username", description="用户名"),
):
    """获取用户对话主题列表

    Args:
        page: 页码
        page_size: 每页数量
        username: 从请求头获取的用户名

    Returns:
        NlResponse: 包含主题列表的响应
    """

    topic_list = await get_chat_topics_by_username(username, page, page_size)

    return NlResponse(
        content={
            "topics": [
                {
                    "id": t.id,
                    "session_id": t.session_id,
                    "username": t.username,
                    "title": t.title,
                    "description": t.description,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "updated_at": t.updated_at.isoformat() if t.updated_at else None,
                }
                for t in topic_list
            ],
        },
        message="success",
    )
