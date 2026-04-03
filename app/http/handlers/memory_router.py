from pydantic import BaseModel, Field

from app.http.handlers.base import router
from app.http.response import NlResponse
from core.logger import setup_logger

logger = setup_logger("memory_router")


# ============ 请求模型 ============

class MemoryAddRequest(BaseModel):
    messages: list[dict[str, str]]
    user_id: str = ""
    session_id: str = ""
    infer: bool = True
    auto_detect_conflict: bool = True


class MemorySearchRequest(BaseModel):
    query: str
    user_id: str = ""
    top_k: int = 10
    use_reranker: bool = True


class MemoryOrganizeRequest(BaseModel):
    user_id: str = ""


# ============ 路由 ============

@router.post("/memory/add")
async def add_memory(req: MemoryAddRequest) -> NlResponse:
    from core.memory.nl_memory import client

    memory = client()
    result = await memory.add(
        messages=req.messages,
        user_id=req.user_id or None,
        session_id=req.session_id or None,
        infer=req.infer,
        auto_detect_conflict=req.auto_detect_conflict,
    )
    return NlResponse.success(content=result, message="success")


@router.post("/memory/search")
async def search_memory(req: MemorySearchRequest) -> NlResponse:
    from core.memory.nl_memory import client

    memory = client()
    result = await memory.search(
        query=req.query,
        user_id=req.user_id or None,
        top_k=req.top_k,
        use_reranker=req.use_reranker,
    )
    return NlResponse.success(content=result, message="success")


@router.get("/memory/all")
async def get_all_memories(user_id: str = "", limit: int = 100) -> NlResponse:
    from core.memory.nl_memory import client

    memory = client()
    result = await memory.get_all(user_id=user_id or None, limit=limit)
    return NlResponse.success(content=result, message="success")


@router.delete("/memory/{memory_id}")
async def delete_memory(memory_id: str) -> NlResponse:
    from core.memory.nl_memory import client

    memory = client()
    result = await memory.delete(memory_id)
    return NlResponse.success(content=result, message="success")


@router.post("/memory/organize")
async def organize_memory(req: MemoryOrganizeRequest) -> NlResponse:
    """
    异步整理任务：遍历记忆，检测并解决冲突。
    """
    from core.memory.nl_memory import client

    memory = client()
    result = await memory.organize(user_id=req.user_id or None)
    return NlResponse.success(content=result, message="success")
