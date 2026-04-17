from core.model.chat_history_repo import add_chat_history
import asyncio

"""聊天记录保存中间件。

在 Agent 完成回复后，从 state 中提取用户问题和 AI 回答，
异步保存到数据库。
"""

from typing import Any

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langgraph.runtime import Runtime

from core.logger import setup_logger
from core.nl_chat.middlewares.common import (
    get_role_name,
    get_latest_human_message,
    get_latest_ai_message,
)

logger = setup_logger(__name__)


class ChatHistorySaverMiddleware(AgentMiddleware):
    """聊天记录保存中间件，在 Agent 完成回复后异步保存完整对话记录。"""

    async def aafter_agent(
        self, state: AgentState, runtime: Runtime
    ) -> dict[str, Any] | None:
        """Agent 执行后，保存完整的聊天记录。"""
        session_id = state.get("session_id", "unknown")
        messages = state.get("messages", [])

        # 从 messages 中提取用户问题和 AI 回答
        user_question = get_latest_human_message(messages)
        ai_answer = get_latest_ai_message(messages)

        if not user_question:
            logger.warning(f"未找到用户消息，跳过保存聊天记录 (session: {session_id})")
            return None

        # count=1 时 get_latest_human_message 返回 str | None
        question_str = user_question if isinstance(user_question, str) else "\n".join(user_question)

        # 获取角色名称
        role = get_role_name(session_id)

        async def _save():
            try:
                await add_chat_history(
                    session_id=session_id,
                    role=role,
                    query=question_str,
                    answer=ai_answer or "",
                )
                logger.info(f"💾 聊天记录已保存 (session: {session_id})")
            except Exception as e:
                logger.warning(f"保存聊天记录失败 (session: {session_id}): {e}")

        asyncio.create_task(_save())

        return None
