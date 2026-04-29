from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from core.model.emotion_speculate_repo import add_emotion_speculate
from langgraph.runtime import Runtime
from core.logger import setup_logger
from typing import Any
from pydantic import BaseModel, Field
import asyncio
import random

from core.nl_chat.middlewares.common import (
    message_bus,
    get_role_name,
    get_latest_human_message,
    build_llm_from_config,
)

logger = setup_logger(__name__)


class EmotionAnalysisResult(BaseModel):
    """情绪分析结果模型。"""

    current_mood: str = Field(description="当前情绪状态")
    warning_type: str = Field(description="警告类型")
    score: float = Field(description="情绪健康分数 (0-1，越高越好)")
    reasons: list[str] = Field(default_factory=list, description="分析原因")
    related_chats: list[str] = Field(default_factory=list, description="相关对话片段")
    suggestions: list[str] = Field(default_factory=list, description="建议")


EMOTION_ANALYSIS_PROMPT = """/nothink 你是一个专业的情绪分析师。请根据用户的对话内容，分析其情绪状态。

## score 评分标准（必须严格遵守）

score 是 0 到 1 之间的浮点数，代表情绪健康程度：

- 0.8 ~ 1.0：积极情绪（开心、兴奋、满足、感激、自信等）
- 0.6 ~ 0.8：平静或中性情绪（平和、正常、无明显波动）
- 0.4 ~ 0.6：轻微负面情绪（轻微烦恼、些许疲惫、小郁闷）
- 0.2 ~ 0.4：明显负面情绪（焦虑、沮丧、失落、愤怒、难过）
- 0.0 ~ 0.2：严重负面情绪（极度悲伤、绝望、崩溃、强烈愤怒）

**重要**：积极情绪的 score 一定大于 0.6，负面情绪的 score 一定小于 0.6。不要搞反！

## 分析要求

参考json格式：
{
  "current_mood": "开心",
  "warning_type": "无",
  "score": 0.85,
  "reasons": ["用户表达了满足和喜悦的情绪", "对话中多次出现积极词汇"],
  "related_chats": ["太好了，今天的事情终于搞定了！", "感觉很有成就感"],
  "suggestions": ["继续保持积极的心态", "可以和朋友分享这份喜悦"]
}

1. current_mood：用简短词语描述用户当前的主要情绪（如：开心、平静、焦虑、沮丧等）
2. warning_type：情绪正常填"无"；存在负面情绪风险填具体类型（如：焦虑倾向、情绪低落等）
3. score：严格按照上述评分标准打分
4. reasons：简要说明判断依据，1-3 条
5. related_chats：引用对话中反映情绪的具体语句，1-3 条
6. suggestions：score < 0.6 时给出 1-2 条改善建议；score >= 0.6 时填空列表"""


class EmotionSpeculateMiddleware(AgentMiddleware):
    def __init__(self):
        self._llm = build_llm_from_config("profile", temperature=0.7)

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

            response = await self._llm.agenerate([messages])
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

            emotion_data = analysis_result.model_dump()

            # score 值范围校验：确保 score 在 0~1 之间
            score = emotion_data.get("score", 0.5)
            if score < 0:
                score = random.uniform(0, 0.3)
                logger.warning(
                    f"score={emotion_data.get('score')} < 0，已随机重置为 {score:.4f}"
                )
            elif score > 1:
                score = random.uniform(0.8, 1.0)
                logger.warning(
                    f"score={emotion_data.get('score')} > 1，已随机重置为 {score:.4f}"
                )
            emotion_data["score"] = score

            message_bus.send(
                "EmotionSpeculateMiddleware",
                message={
                    "type": "emotion",
                    "session_id": session_id,
                    "emotion_analysis": emotion_data,
                },
            )

            # 直接存储到数据库
            role = get_role_name(session_id)
            await add_emotion_speculate(
                session_id=session_id,
                role=role,
                query=user_question,
                emotion=emotion_data,
            )
            logger.info(f"💾 情感分析记录已保存 (session: {session_id})")

        except Exception as e:
            logger.error(f"❌ 情感分析失败 (session: {session_id}): {e}", exc_info=True)

    async def abefore_model(
        self, state: AgentState, runtime: Runtime
    ) -> dict[str, Any] | None:
        # 直接从 state 中获取 session_id
        session_id = state.get("session_id", "unknown")
        logger.info(f"[开始处理会话: {session_id}]")
        messages = state.get("messages", [])
        user_question = get_latest_human_message(messages, 3)
        if isinstance(user_question, list):
            user_question = "\n".join(user_question)

        if user_question is None:
            logger.warning("未找到用户消息")
            return None

        logger.info(f"📝 用户问题 (session: {session_id}): {user_question}")

        # 创建后台任务执行情感分析（不阻塞主流程）
        asyncio.create_task(self._analyze_emotion_async(user_question, session_id))

        # 立即返回，不等待情感分析完成
        return None
