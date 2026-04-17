from core.logger import setup_logger
from pydantic import BaseModel
from app.http.handlers.base import router
from fastapi import Request
from fastapi.responses import StreamingResponse
from app.http.response import NlResponse
from core.model.user_repo import get_user_by_session_id
from core.nl_chat.chat import ChatAgent
from core.helper.bprint import log_table


logger = setup_logger("chat_router")

# 创建全局 ChatAgent 实例
_chat_agent = None


def get_chat_agent() -> ChatAgent:
    """获取 ChatAgent 单例"""
    global _chat_agent
    if _chat_agent is None:
        _chat_agent = ChatAgent()
    return _chat_agent


class NLAIChatRequest(BaseModel):
    model: str
    messages: list[dict[str, object]]
    temperature: float = 0.7
    top_p: float = 0.5
    stream: bool = True


@router.post("/chat/completions")
async def chat(request: Request, nl_request: NLAIChatRequest):

    # 打印请求所有的头部参数
    for key, value in request.headers.items():
        logger.info(f"[/chat/completions] Request header - {key}: {value}")

    authorization = request.headers.get("authorization", "")
    if authorization.startswith("Bearer "):
        session_id = authorization[len("Bearer ") :]
    else:
        session_id = authorization

    if not session_id:
        logger.warning("[/chat/completions] session_id 和 authorization 均为空")
        return NlResponse(
            content={},
            message="session_id is required in header",
            status_code=400,
        )

    logger.info(f"[/chat/completions] 解析到 session_id: {session_id}")

    # 通过session_id 获取 user_id
    user_id = await get_user_by_session_id(session_id)
    if user_id is None:
        logger.warning(
            f"[/chat/completions] session_id 无效，未找到对应用户: {session_id}"
        )
        return NlResponse(
            content={},
            message="session_id is invalid",
            status_code=400,
        )

    log_table(
        logger,
        "Chat Request",
        {
            "session_id": session_id,
            "model": nl_request.model,
            "messages_count": len(nl_request.messages),
            "temperature": nl_request.temperature,
            "top_p": nl_request.top_p,
        },
    )

    # 从消息中提取用户问题（最后一条消息）
    if not nl_request.messages:
        logger.warning(f"[/chat/completions] messages 为空, session_id: {session_id}")
        return NlResponse(
            content={},
            message="messages is required",
            status_code=400,
        )

    last_message = nl_request.messages[-1]
    question = str(last_message.get("content", ""))

    agent = get_chat_agent()

    return StreamingResponse(
        agent.chat_stream(
            model=nl_request.model,
            session_id=session_id,
            user_id=user_id,
            question=question,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲
        },
    )
