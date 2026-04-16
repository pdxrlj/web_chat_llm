import asyncio
import warnings
from typing import Any
from langchain.agents import AgentState
from langgraph.runtime import Runtime
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from pydantic import Field, BaseModel
from core.model.topic_repo import save_chat_topic
from core.nl_chat.middlewares.common import message_bus, build_llm_from_config
from core.logger import setup_logger

logger = setup_logger(__name__)

TOPIC_ANALYSIS_PROMPT = """你是一个专业的主题分析器。请根据对话内容分析用户的主要主题。

分析要求：
1. 识别用户当前的主要主题（如：技术问题、情感咨询、一般对话等）
2. 给出主题分类（如：技术支持、情感支持、一般咨询等）
3. 分析原因并提供相关对话片段
4. 回复长度控制在 20 字符内

输出要求：
- 必须使用JSON格式返回结果
- 包含topic字段，值为分析出的主题
- 包含description字段，值为分析出的主题描述
- 示例输出：{"topic":"技术问题","description":"用户在询问关于技术问题的内容"}

请根据用户的问题进行专业的主题分析。"""


class TopicAnalysisResult(BaseModel):
    topic: str = Field(description="分析出的主题")
    description: str = Field(description="分析出的主题描述")


class ChatTopicMiddleware(AgentMiddleware):
    """对话主题分析中间件，每积累一定数量的消息后自动分析对话主题。"""

    # 触发主题分析的消息缓存阈值
    CACHE_THRESHOLD = 2

    def __init__(self):
        self.cache: list[BaseMessage] = []
        self._llm = build_llm_from_config("topic", temperature=0.1)

    def _topic_prompt(
        self, user_question: list[BaseMessage]
    ) -> list[BaseMessage] | None:
        # 收集所有相关的对话消息（人类消息和AI消息）
        conversation_history = []
        for msg in user_question:
            if isinstance(msg, (HumanMessage, AIMessage)):
                conversation_history.append(msg)

        # 如果没有对话历史，返回 None
        if not conversation_history:
            logger.warning("未找到对话历史，无法进行主题分析")
            return None

        messages = [
            SystemMessage(content=TOPIC_ANALYSIS_PROMPT),
            HumanMessage(
                content="\n".join(
                    [
                        f"{'用户' if isinstance(msg, HumanMessage) else '助手'}: {msg.content}"
                        for msg in conversation_history
                    ]
                )
            ),
        ]

        return messages

    async def _topic_analysis(self, session_id: str, user_question: list[BaseMessage]):
        """异步执行主题分析（后台任务，不阻塞主流程）

        Args:
            user_question: 用户问题
            session_id: 会话 ID
        """
        try:
            logger.info(f"开始主题分析 (session: {session_id})")

            messages = self._topic_prompt(user_question)
            if messages is None:
                return

            topic_llm = self._llm
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message=".*PydanticSerializationUnexpectedValue.*",
                    category=UserWarning,
                )
                struct_llm = topic_llm.with_structured_output(TopicAnalysisResult)
                response = await struct_llm.ainvoke(messages)

            if not isinstance(response, TopicAnalysisResult):
                logger.warning(
                    f"主题分析结果类型异常，跳过 (session: {session_id}): {type(response)}"
                )
                return

            logger.info(f"主题分析结果 (session: {session_id}): {response}")

            message_bus.send(
                "ChatTopicMiddleware",
                message={
                    "type": "topic",
                    "session_id": session_id,
                    "topic_analysis": response.model_dump(),
                },
            )

            await save_chat_topic(
                session_id=session_id,
                username=session_id,
                title=response.topic,
                description=response.description,
            )
        except Exception as e:
            logger.error(f"主题分析失败 (session: {session_id}): {e}", exc_info=True)

    async def aafter_agent(
        self, state: AgentState, runtime: Runtime
    ) -> dict[str, Any] | None:
        """Agent 执行后的钩子，积累消息达到阈值后触发主题分析。"""
        messages = state.get("messages", [])
        if not messages:
            return None

        self.cache.append(messages[-1])

        if len(self.cache) < self.CACHE_THRESHOLD:
            return None

        session_id = state.get("session_id", "unknown")

        cache_snapshot = self.cache
        self.cache = []

        asyncio.create_task(
            self._topic_analysis(session_id=session_id, user_question=cache_snapshot)
        )

        return None
