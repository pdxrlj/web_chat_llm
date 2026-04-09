"""对话摘要中间件

当对话历史超过 token 阈值时自动摘要历史消息，防止上下文过长。
"""

from core.logger import setup_logger
from langchain_core.messages import HumanMessage, SystemMessage, AnyMessage
from langchain_openai import ChatOpenAI
from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from typing import Any

logger = setup_logger(__name__)


class SummarizationMiddleware(AgentMiddleware):
    """对话摘要中间件 - 当对话超过阈值时自动摘要历史消息

    该中间件会在调用模型前检查对话历史的长度，如果超过指定的 token 阈值，
    则会自动将旧消息摘要成一条系统消息，保留最近的消息。

    Args:
        summary_model: 用于生成摘要的 LLM 模型
        trigger_tokens: 触发摘要的 token 数量阈值，默认 4000
        keep_messages: 保留最近的消息数量，默认 4

    Example:
        ```python
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(model="gpt-4")
        middleware = SummarizationMiddleware(
            summary_model=llm,
            trigger_tokens=4000,
            keep_messages=4
        )
        ```
    """

    def __init__(
        self,
        summary_model: ChatOpenAI,
        trigger_tokens: int = 4000,
        keep_messages: int = 4,
    ):
        super().__init__()
        self.summary_model = summary_model
        self.trigger_tokens = trigger_tokens
        self.keep_messages = keep_messages

    async def abefore_model(
        self, state: AgentState, runtime: Any = None
    ) -> dict[str, Any] | None:
        """在调用模型前执行摘要逻辑

        Args:
            state: Agent 状态，包含 messages 字段
            runtime: 运行时上下文（可选）

        Returns:
            状态更新字典或 None（表示不更新）
        """
        messages = state.get("messages", [])

        # 估算 token 数量（简单估算：字符数 / 4）
        total_chars = sum(
            len(msg.content) for msg in messages if hasattr(msg, "content")
        )
        estimated_tokens = total_chars // 4

        # 如果超过阈值，进行摘要
        if (
            estimated_tokens > self.trigger_tokens
            and len(messages) > self.keep_messages
        ):
            logger.info(
                f"触发摘要 - 估算 tokens: {estimated_tokens}, "
                f"消息数: {len(messages)}, 保留: {self.keep_messages}"
            )

            # 保留最近的消息
            recent_messages = messages[-self.keep_messages :]
            old_messages = messages[: -self.keep_messages]

            # 生成摘要
            if old_messages:
                summary_text = await self._summarize_messages(old_messages)

                # 创建摘要消息
                summary_message = SystemMessage(
                    content=f"对话历史摘要：\n{summary_text}"
                )

                # 返回更新后的消息列表
                logger.info(
                    f"摘要完成 - 原始消息数: {len(messages)}, "
                    f"新消息数: {len([summary_message] + recent_messages)}"
                )
                return {"messages": [summary_message] + recent_messages}

        return None

    async def _summarize_messages(self, messages: list[AnyMessage]) -> str:
        """生成消息摘要

        Args:
            messages: 需要摘要的消息列表

        Returns:
            摘要文本
        """
        # 构建摘要 prompt
        conversation = "\n".join(
            [
                f"{msg.type}: {msg.content}"
                for msg in messages
                if hasattr(msg, "content")
            ]
        )

        summary_prompt = f"""请总结以下对话内容，保留关键信息和上下文：

{conversation}

摘要："""

        try:
            response = await self.summary_model.ainvoke(
                [HumanMessage(content=summary_prompt)],
                extra_body={"enable_thinking": False},
            )
            # 处理 content 可能是字符串或列表的情况
            content = response.content
            if isinstance(content, str):
                return content
            elif isinstance(content, list):
                # 如果是列表，提取文本内容
                return " ".join(str(item) for item in content)
            else:
                return str(content)
        except Exception as e:
            logger.error(f"摘要生成失败: {e}")
            return "历史对话摘要生成失败"
