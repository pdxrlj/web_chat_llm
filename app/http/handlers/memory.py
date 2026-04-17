"""记忆报告接口：根据 session_id 获取用户记忆，使用 LLM 生成分析报告。"""

from app.http.handlers.base import router
from app.http.response import NlResponse
from core.logger import setup_logger
from core.model.user_repo import get_user_by_session_id
from core.memory.nl_memory import client as memory_client
from core.nl_chat.middlewares.common import build_llm_from_config
from fastapi import Request

logger = setup_logger("memory_handler")

_REPORT_PROMPT = """你是一位专业的用户画像分析师。请根据以下用户记忆数据，生成一份简洁、真实的用户分析报告。

要求：
1. 基于记忆内容客观分析，不要编造没有依据的结论
2. 报告内容精简，不超过 200 字
3. 从兴趣偏好、性格特征、沟通风格等维度总结
4. 如果记忆数据不足，如实说明，不要强行推测
5. 输出文本格式，不要包含任何 Markdown 语法，也不要包含任何 HTML 标签，只输出普通文本。

用户记忆数据：
{memories}
"""


@router.get("/memory/report")
async def get_memory_report(request: Request):
    """根据 session_id 获取用户记忆并生成分析报告。"""

    # 从 header 解析 session_id（与 chat_router 逻辑保持一致）
    session_id = request.headers.get("session_id")
    if not session_id:
        authorization = request.headers.get("authorization", "")
        if authorization.startswith("Bearer "):
            session_id = authorization[len("Bearer "):]
        else:
            session_id = authorization

    if not session_id:
        return NlResponse.fail(
            content={}, message="session_id is required", status_code=400
        )

    logger.info(f"[memory/report] 解析到 session_id: {session_id}")

    # 通过 session_id 获取 user_id
    user_id = await get_user_by_session_id(session_id)
    if user_id is None:
        logger.warning(f"[memory/report] session_id 无效: {session_id}")
        return NlResponse.fail(
            content={}, message="session_id is invalid", status_code=400
        )

    try:
        # 获取用户全部记忆
        mem = memory_client()
        result = await mem.get_all(user_id=str(user_id), limit=10000)
        memories = result.get("memories", [])

        if not memories:
            return NlResponse.success(
                content={
                    "report": "暂无足够的记忆数据，无法生成报告。",
                    "memory_count": 0,
                }
            )

        # 拼接记忆内容
        memory_texts = [
            f"- [{m.get('memory_type', 'unknown')}] {m.get('content', '')}"
            for m in memories
        ]
        memories_str = "\n".join(memory_texts)

        # 使用 memory 模型生成报告
        llm = build_llm_from_config("memory", temperature=0.3)
        prompt = _REPORT_PROMPT.format(memories=memories_str)
        response = await llm.ainvoke(prompt)

        raw_content = (
            response.content if hasattr(response, "content") else str(response)
        )
        if isinstance(raw_content, list):
            report_text = " ".join(
                part.get("text", "")
                for part in raw_content
                if isinstance(part, dict) and part.get("type") == "text"
            )
        else:
            report_text = str(raw_content).strip()

        logger.info(
            f"[memory/report] 报告生成成功, session: {session_id}, 记忆数: {len(memories)}"
        )

        return NlResponse.success(
            content={"report": report_text, "memory_count": len(memories)}
        )

    except Exception as e:
        logger.error(f"[memory/report] 生成报告失败: {e}", exc_info=True)
        return NlResponse.fail(
            content={}, message=f"生成报告失败: {e}", status_code=500
        )
