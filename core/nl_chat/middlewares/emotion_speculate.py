from blinker import signal
from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.runtime import Runtime
from pydantic import SecretStr
from core.config import config, LLMConfig
from core.logger import setup_logger
from typing import Any, Optional
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
import asyncio

logger = setup_logger(__name__)


message_bus = signal("we_chat")


# @message_bus.connect
# def on_message(sender, message: dict):
#     """
#     处理消息事件
#     :param sender: 发送者
#     :param message: 消息内容
#     """
#     print(f"收到消息: {message}")
class EmotionAnalysisResult(BaseModel):
    """情绪分析结果模型。"""

    current_mood: str = Field(description="当前情绪状态")
    warning_type: str = Field(description="警告类型")
    score: float = Field(description="情绪健康分数 (0-1，越高越好)")
    reasons: list[str] = Field(default_factory=list, description="分析原因")
    related_chats: list[str] = Field(default_factory=list, description="相关对话片段")
    suggestions: list[str] = Field(default_factory=list, description="建议")


EMOTION_ANALYSIS_PROMPT = """/nothink 你是一个专业的情绪分析师。请根据对话内容分析用户的情绪状态。

分析要求：
1. 识别用户当前的主要情绪（如：平静、焦虑、开心、沮丧、愤怒等）
2. 判断是否需要预警（如：负面情绪严重、需要关注等）
3. 给出情绪健康分数（0-1，越高表示情绪状态越好）
4. 分析原因并提供相关对话片段
5. 给出适当的建议

请根据用户的问题进行专业的情感分析。"""


class EmotionSpeculateMiddleware(AgentMiddleware):
    def __init__(self):
        self.emotion_llm_config = config.get_llm("emotion")
        if not self.emotion_llm_config:
            raise ValueError("emotion LLM 配置不存在")

    def _emotion_llm(self):
        # 构建参数，确保类型安全
        if not isinstance(self.emotion_llm_config, LLMConfig):
            raise TypeError("emotion LLM 配置类型错误")

        chat_kwargs = {
            "model": self.emotion_llm_config.model,
            "base_url": self.emotion_llm_config.base_url,
            "temperature": 0.7,
            "extra_body": {"enable_thinking": False},
        }

        if self.emotion_llm_config.api_key:
            chat_kwargs["api_key"] = SecretStr(self.emotion_llm_config.api_key)

        return ChatOpenAI(**chat_kwargs)

    def _emotion_prompt(self, user_question: str) -> list[BaseMessage]:
        messages = [
            SystemMessage(content=EMOTION_ANALYSIS_PROMPT),
            HumanMessage(content=user_question),
        ]

        return messages

    async def _analyze_emotion_async(self, user_question: str, session_id: str) -> None:
        """异步执行情感分析（后台任务，不阻塞主流程）

        Args:
            user_question: 用户问题
            session_id: 会话 ID
        """
        try:
            logger.info(
                f"🔍 开始情感分析 (session: {session_id}): {user_question[:50]}..."
            )

            # 构建消息和 LLM
            messages = self._emotion_prompt(user_question)
            llm = self._emotion_llm()

            # 直接使用传统方法（NLEmotion 模型不支持 Function Calling）
            response = await llm.agenerate([messages])
            response_text = response.generations[0][0].text

            # 检查响应是否为空
            if not response_text or not response_text.strip():
                logger.warning(f"LLM 返回空响应，跳过情感分析 (session: {session_id})")
                return

            # 检查响应长度，避免过长的 JSON
            if len(response_text) > 10000:
                logger.warning(
                    f"LLM 响应过长 ({len(response_text)} 字符)，跳过情感分析 (session: {session_id})"
                )
                return

            logger.debug(f"LLM 原始回复: {response_text[:200]}...")

            # 尝试提取并解析 JSON
            import re

            # 提取 markdown 代码块或第一个 JSON 对象
            json_match = re.search(
                r"```json\s*(\{.*?\})\s*```", response_text, re.DOTALL
            ) or re.search(r"\{.*\}", response_text, re.DOTALL)
            json_text = (
                json_match.group(1)
                if json_match and json_match.lastindex
                else (json_match.group(0) if json_match else response_text.strip())
            )

            try:
                analysis_result = EmotionAnalysisResult.model_validate_json(json_text)
            except Exception as parse_error:
                logger.warning(
                    f"JSON 解析失败，跳过情感分析 (session: {session_id}): {parse_error}"
                )
                return

            logger.info(f"✅ 情感分析结果 (session: {session_id}): {analysis_result}")

            message_bus.send(
                "EmotionSpeculateMiddleware",
                message={
                    "type": "emotion",
                    "session_id": session_id,
                    "emotion_analysis": analysis_result.model_dump(),
                },
            )

        except Exception as e:
            logger.error(f"❌ 情感分析失败 (session: {session_id}): {e}", exc_info=True)

    async def abefore_model(
        self, state: AgentState, runtime: Runtime
    ) -> dict[str, Any] | None:
        # 直接从 state 中获取 session_id
        session_id = state.get("session_id", "unknown")
        logger.info(f"[开始处理会话: {session_id}]")
        messages = state.get("messages", [])
        user_question: Optional[str] = None

        # 从后往前找最新的 HumanMessage
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                # 处理 content 可能是字符串或列表的情况
                if isinstance(msg.content, str):
                    user_question = msg.content
                else:
                    # 如果是列表，转换为字符串
                    user_question = str(msg.content)
                break

        if user_question is None:
            logger.warning("未找到用户消息")
            return None

        logger.info(f"📝 用户问题 (session: {session_id}): {user_question}")

        # 创建后台任务执行情感分析（不阻塞主流程）
        asyncio.create_task(self._analyze_emotion_async(user_question, session_id))

        # 立即返回，不等待情感分析完成
        return None
