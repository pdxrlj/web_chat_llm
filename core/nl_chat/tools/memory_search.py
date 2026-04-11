from langchain_core.tools import tool
from core.memory import nl_memory


@tool
async def search_memory(query: str, user_id: str) -> str:
    """搜索用户的相关记忆信息。用于获取用户偏好、历史事件等上下文信息。

    Args:
        query: 搜索查询内容
        user_id: 用户ID

    Returns:
        相关记忆的文本内容
    """
    memory_client = nl_memory.client()
    results = await memory_client.search(query=query, user_id=user_id, top_k=5)

    if results["results"]:
        memories = [r["content"] for r in results["results"]]
        return "\n".join(memories)
    return "未找到相关记忆"
