from core.logger import setup_logger
from pydantic import BaseModel
from app.http.handlers.base import router
from fastapi import Request
from fastapi.responses import StreamingResponse
from app.http.response import NlResponse
from core.nl_chat.chat import ChatAgent

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
    stream: bool = True  # 兼容 OpenAI 格式


@router.post("/chat/completions")
async def chat(request: Request, nl_request: NLAIChatRequest):
    # 从请求头获取 session_id（必填）
    session_id = request.headers.get("session_id")

    if not session_id:
        return NlResponse(
            content={},
            message="session_id is required in header",
            status_code=400,
        )

    logger.info(
        " ".join(
            [
                "Chat request -",
                f"session_id: {session_id},",
                f"model: {nl_request.model},",
                f"messages_count: {len(nl_request.messages)},",
                f"temperature: {nl_request.temperature},",
                f"top_p: {nl_request.top_p}",
            ]
        )
    )

    # 从消息中提取用户问题（最后一条消息）
    if not nl_request.messages:
        return NlResponse(
            content={},
            message="messages is required",
            status_code=400,
        )

    last_message = nl_request.messages[-1]
    question = str(last_message.get("content", ""))

    # 获取 ChatAgent 实例
    agent = get_chat_agent()

    # 返回流式响应
    return StreamingResponse(
        agent.chat_stream(
            model=nl_request.model,
            session_id=session_id,
            question=question,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲
        },
    )
