from core.logger import setup_logger
from pydantic import BaseModel
from app.http.handlers.base import router
from fastapi import Request
from app.http.response import NlResponse

logger = setup_logger("chat_router")


class NLAIChatRequest(BaseModel):
    model: str
    messages: list[dict[str, object]]
    temperature: float = 0.7
    top_p: float = 0.5


@router.post("/chat/completions")
async def chat(request: Request, nl_request: NLAIChatRequest):
    session_id = request.headers.get("session_id")
    session_id = session_id.replace("Bearer ", "") if session_id else None

    if not session_id:
        return NlResponse(
            content={},
            message="session_id is required",
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

    return NlResponse(
        content={},
        message="success",
        status_code=200,
    )
