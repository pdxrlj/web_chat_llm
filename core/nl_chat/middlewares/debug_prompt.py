"""调试中间件：打印最终发送给模型的完整提示词"""

from core.logger import setup_logger
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse

import json

logger = setup_logger(__name__)


class DebugPromptMiddleware(AgentMiddleware):
    """调试中间件：在模型调用前打印完整的 system_message 和 messages"""

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler,
    ) -> ModelResponse:
        """在模型调用前打印完整的 system_message 和 messages"""
        logger.info(f"{'=' * 60}")
        logger.info("🔍 [DEBUG] 最终发送给模型的提示词")
        logger.info(f"{'=' * 60}")
        if request.system_message:
            sys_content = request.system_message.content
            if isinstance(sys_content, list):
                sys_content = json.dumps(sys_content, ensure_ascii=False)
            logger.info(f"  [SYSTEM_MESSAGE] ({len(sys_content)} 字符)\n{sys_content}")
        else:
            logger.info("  [SYSTEM_MESSAGE] (无)")
        for i, msg in enumerate(request.messages):
            role = msg.type.upper()
            content = (
                msg.content
                if isinstance(msg.content, str)
                else json.dumps(msg.content, ensure_ascii=False)
            )
            logger.info(f"  [MSG {i}] [{role}] {content}")
        tool_names = [
            t.name if hasattr(t, "name") else t.get("name", str(t))  # type: ignore[union-attr]
            for t in request.tools
        ]
        logger.info(f"  [TOOLS] {tool_names}")
        logger.info(f"{'=' * 60}")
        return await handler(request)
