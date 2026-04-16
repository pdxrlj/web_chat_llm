"""
聊天记录分析代理。

根据 session_id 查询聊天记录，
使用 LLM 生成结构化分析报告，通过 SSE 推送给客户端。
"""

import json
from datetime import datetime
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from core.logger import setup_logger
from core.model.chat_analyze_repo import add_chat_analyze
from core.model.chat_history_repo import get_chat_histories_by_session_id
from core.nl_chat.middlewares.common import build_llm_from_config, get_role_name, message_bus

logger = setup_logger(__name__)


# ---------------------------------------------------------------------------
# 结构化输出模型
# ---------------------------------------------------------------------------


class StatusCard(BaseModel):
    key: str = Field(description="卡片标识")
    title: str = Field(description="卡片标题")
    value: str = Field(description="卡片值，简洁结论")
    level: str = Field(description="等级：good / normal / weak")


class UserPortrait(BaseModel):
    personality: str = Field(description="阶段性性格观察")
    preferences: list[str] = Field(default_factory=list, description="偏好")
    dislikes: list[str] = Field(default_factory=list, description="不喜欢的事物")
    advice: str = Field(description="温和可执行的建议")


class KeyMoment(BaseModel):
    moment_type: str = Field(description="瞬间类型")
    title: str = Field(description="标题")
    summary: str = Field(description="简述")


class EmotionPoint(BaseModel):
    date: str = Field(description="日期")
    score: int = Field(description="情绪分数")
    emotion: str = Field(description="情绪标签")
    trigger_summary: str = Field(description="触发原因简述")


class EmotionTrend(BaseModel):
    points: list[EmotionPoint] = Field(default_factory=list, description="情绪趋势点")
    summary: str = Field(description="情绪趋势总结")
    advice: str = Field(description="情绪建议")


class AlertType(BaseModel):
    type: str = Field(description="告警类型")
    count: int = Field(description="出现次数")


class SafetyAlert(BaseModel):
    alert_count: int = Field(default=0, description="告警总数")
    alert_types: list[AlertType] = Field(default_factory=list, description="告警类型统计")
    summary: str = Field(description="安全总结")


class Suggestion(BaseModel):
    title: str = Field(description="建议标题")
    content: str = Field(description="建议内容")


class Script(BaseModel):
    scenario: str = Field(description="场景")
    script: str = Field(description="话术")


class ChatAnalyzeReport(BaseModel):
    """聊天记录分析报告结构化模型。"""

    summary_text: str = Field(description="整体状态概括")
    status_cards: list[StatusCard] = Field(default_factory=list, description="状态卡片")
    user_portrait: UserPortrait = Field(description="用户画像观察")
    key_moments: list[KeyMoment] = Field(default_factory=list, description="重要瞬间")
    emotion_trend: EmotionTrend = Field(description="情绪趋势")
    safety_alert: SafetyAlert = Field(description="安全告警")
    next_week_suggestions: list[Suggestion] = Field(default_factory=list, description="建议")
    scripts: list[Script] = Field(default_factory=list, description="话术")
    closing_text: str = Field(description="结尾语")


# ---------------------------------------------------------------------------
# ORM 字段安全提取
# ---------------------------------------------------------------------------


def _get_created_at(record: Any) -> datetime | None:
    val = record.created_at  # type: ignore[union-attr]
    if val is None or not isinstance(val, datetime):
        return None
    return val


def _get_role(record: Any) -> str:
    val = record.role  # type: ignore[union-attr]
    return str(val) if val is not None else ""


def _get_query(record: Any) -> str:
    val = record.query  # type: ignore[union-attr]
    return str(val) if val is not None else ""


def _get_answer(record: Any) -> str:
    val = record.answer  # type: ignore[union-attr]
    return str(val) if val is not None else ""


def _to_chat_record(record: Any) -> dict[str, str]:
    """将 ORM 记录转为简洁的聊天记录字典。"""
    dt = _get_created_at(record)
    return {
        "role": _get_role(record),
        "content": (_get_query(record) or _get_answer(record))[:200],
        "created_at": dt.isoformat() if dt is not None else "",
    }


# ---------------------------------------------------------------------------
# 数据收集：仅查询聊天记录
# ---------------------------------------------------------------------------


async def _collect_chat_records(session_id: str) -> list[dict[str, str]]:
    """查询指定 session_id 的全部聊天记录。"""
    all_records: list[Any] = []
    page = 1
    page_size = 200
    while True:
        records = await get_chat_histories_by_session_id(
            session_id=session_id, page=page, page_size=page_size
        )
        if not records:
            break
        all_records.extend(records)
        if len(records) < page_size:
            break
        page += 1

    return [_to_chat_record(r) for r in all_records]


# ---------------------------------------------------------------------------
# 提示词
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """你是"聊天记录分析助手"。

请基于输入的聊天记录，生成一份结构化分析结果。
你的任务是：从聊天记录中提取事实，整理成"温暖、克制、非评判"的结构化内容。

核心原则：
1. 所有输出必须基于聊天记录内容，不可编造。
2. 风格温暖、克制、非评判，避免医疗化、监控化表达。
3. 聊天记录不足时，不强行总结，不夸大，不补脑。
4. 聊天记录充分时，可以输出更自然、更完整的总结。

表达分级：
- 聊天记录充足（≥20条）：可做阶段性总结，概括互动特点、偏好、变化，但不可长期定性。
- 聊天记录一般（8-19条）：只做局部总结，语言保守，如"从已有记录来看""目前留下的信息显示"。
- 聊天记录较少（<8条）：以"记录有限""期待更多互动"为主，不强行生成丰满画像。

文案风格：
1. 总结性字段要像"观察"，不是"系统播报"。
2. 优先用："从已有记录来看 / 可以看到 / 慢慢 / 一点点"
3. 避免用："系统监测显示 / 判定为 / 明显存在 / 已证实 / 高风险 / 严重 / 异常"
4. 避免给用户贴标签，避免性格长期定性。
5. 优先表达"看见变化、看见节奏、看见努力"，不强调比较和评估。

约束：
1. 严禁编造对话中未出现的事实。
2. 证据不足时优先保守表述。
3. 数组无数据输出空列表，数值无数据输出0，字符串无数据输出空字符串。"""


# ---------------------------------------------------------------------------
# AnalyzeAgent
# ---------------------------------------------------------------------------


class AnalyzeAgent:
    """聊天记录分析代理。

    使用 session_id 查询聊天记录，
    调用 LLM 生成结构化分析报告，通过 SSE 推送给客户端。
    """

    def __init__(self) -> None:
        llm = build_llm_from_config("profile", temperature=0.3)
        self._llm = llm.with_structured_output(ChatAnalyzeReport)

    async def analyze(self, session_id: str) -> ChatAnalyzeReport:
        """分析指定会话的聊天记录并生成结构化报告。"""
        logger.info(f"开始聊天记录分析 - session_id={session_id}")

        # 1. 查询聊天记录
        chat_records = await _collect_chat_records(session_id)
        chat_count = len(chat_records)
        logger.info(f"聊天记录查询完成 - count={chat_count}")

        # 2. 构建消息
        chat_json = json.dumps(chat_records, ensure_ascii=False, default=str)
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"以下是聊天记录（共{chat_count}条）：\n{chat_json}"),
        ]

        # 3. 调用 LLM（structured_output 直接返回 Pydantic 模型）
        try:
            report: ChatAnalyzeReport = await self._llm.ainvoke(messages)  # type: ignore[assignment]
        except Exception as e:
            logger.error(f"LLM 结构化输出失败，尝试手动解析: {e}")
            # 降级：用原始 LLM 调用 + 手动 JSON 解析
            try:
                raw_llm = build_llm_from_config("profile", temperature=0.3)
                response = await raw_llm.ainvoke(messages)
                raw_content = response.content
                if isinstance(raw_content, list):
                    raw_content = "".join(
                        part if isinstance(part, str) else str(part) for part in raw_content
                    )
                raw_content = raw_content.strip()
                report = self._parse_raw_json(raw_content)
            except Exception as fallback_err:
                logger.error(f"LLM 降级调用也失败: {fallback_err}")
                report = self._empty_report()

        # 4. 通过 SSE 推送给客户端
        message_bus.send(
            "AnalyzeAgent",
            message={
                "type": "chat_analyze",
                "session_id": session_id,
                "report": report.model_dump(),
            },
        )

        # 5. 保存到数据库
        try:
            role = get_role_name(session_id)
            await add_chat_analyze(
                session_id=session_id,
                role=role,
                report=report.model_dump(),
            )
            logger.info(f"分析报告已保存 - session_id={session_id}")
        except Exception as e:
            logger.error(f"分析报告保存失败: {e}")

        logger.info(f"聊天记录分析完成 - session_id={session_id}")
        return report

    @staticmethod
    def _parse_raw_json(raw: str) -> ChatAnalyzeReport:
        """从 LLM 原始文本中提取 JSON 并解析为报告模型（降级方案）。"""
        text = raw.strip()
        # 去除 markdown code block
        if text.startswith("```"):
            first_newline = text.index("\n") if "\n" in text else len(text)
            text = text[first_newline + 1 :]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        # 定位最外层 {}
        if not text.startswith("{"):
            brace_start = text.find("{")
            brace_end = text.rfind("}")
            if brace_start != -1 and brace_end > brace_start:
                text = text[brace_start : brace_end + 1]
        try:
            return ChatAnalyzeReport.model_validate_json(text)
        except Exception:
            return AnalyzeAgent._empty_report()

    @staticmethod
    def _empty_report() -> ChatAnalyzeReport:
        """返回空的报告兜底。"""
        return ChatAnalyzeReport(
            summary_text="记录还不算多，暂时难以形成更完整的观察",
            status_cards=[
                StatusCard(key="interaction", title="互动状态", value="互动较少", level="normal"),
                StatusCard(key="expression", title="表达状态", value="记录还在积累中", level="normal"),
            ],
            user_portrait=UserPortrait(
                personality="尚在慢慢了解中",
                preferences=[],
                dislikes=[],
                advice="保持日常聊天节奏，慢慢敞开心扉",
            ),
            key_moments=[],
            emotion_trend=EmotionTrend(
                points=[],
                summary="情绪记录有限",
                advice="可以多聊聊日常小事，慢慢了解情绪节奏",
            ),
            safety_alert=SafetyAlert(
                alert_count=0,
                alert_types=[],
                summary="未发现明显安全风险",
            ),
            next_week_suggestions=[
                Suggestion(title="固定聊天时间", content="每天选一个固定时间聊聊，哪怕只有5分钟"),
                Suggestion(title="从兴趣切入", content="从感兴趣的话题开始，让对话自然展开"),
            ],
            scripts=[],
            closing_text="成长有自己的节奏，陪伴仍在继续",
        )
