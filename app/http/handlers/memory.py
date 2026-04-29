"""记忆报告接口：根据 session_id 获取用户记忆数据。"""

import json

from langchain_core.messages import HumanMessage, SystemMessage

from app.http.handlers.base import router
from app.http.response import NlResponse
from core.logger import setup_logger
from core.model.user_repo import get_user_by_session_id
from core.memory.nl_memory import client as memory_client
from core.nl_chat.middlewares.common import build_llm_from_config
from fastapi import Request

logger = setup_logger("memory_handler")

_MEMORY_REPORT_PROMPT = """你是一位专业的用户画像分析师，请根据用户记忆数据，分析并生成一份结构化报告。

## 输出格式

严格输出以下JSON格式，不要输出任何其他内容：
```json
{
  "basic_info": ["要点1", "要点2"],
  "attention_needed": ["要点1", "要点2"],
  "current_status": ["要点1", "要点2"],
  "recent_events": ["要点1", "要点2"],
  "preferences": ["要点1", "要点2"],
  "current_demands": ["要点1", "要点2"]
}
```

## 字段说明

- basic_info：基础信息，提取用户的基本身份信息，如名字、年龄、性别、职业、所在城市等
- attention_needed：需关注内容，识别需要优先关注的重要信息，包括安全风险、心理危机、紧急需求等；如果检测到危险信号（如自伤、暴力倾向等），必须置顶标注
- current_status：当前状态，推断用户当前的生理和心理状态，如情绪、身体状况、能量水平等
- recent_events：近期事件，梳理用户近期经历的重要事件，按时间或重要性排列
- preferences：偏好与关注，归纳用户的兴趣爱好、饮食偏好、关注的话题等
- current_demands：当前诉求，总结用户当前明确表达或隐含的需求和愿望

## 输出规则
1. 内容必须基于记忆数据，不得编造
2. 每条要点简洁明了，不超过20字
3. 各模块之间不要重复相同内容
4. 如果某个模块没有相关信息，填写空数组 []
5. 只输出JSON，不要输出任何额外文字"""


@router.get("/memory/report")
async def get_memory_report(request: Request):
    """根据 session_id 获取用户记忆并生成分析报告。"""

    # 从 header 解析 session_id（与 chat_router 逻辑保持一致）
    session_id = request.headers.get("session_id")
    if not session_id:
        authorization = request.headers.get("authorization", "")
        if authorization.startswith("Bearer "):
            session_id = authorization[len("Bearer ") :]
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

        # 提取记忆内容用于生成报告
        memory_texts = []
        for m in memories:
            content = m.get("content", "")
            memory_type = m.get("memory_type", "unknown")
            memory_texts.append(f"[{memory_type}] {content}")

        memories_summary = "\n".join(memory_texts)

        # 调用大模型生成分析报告
        llm = build_llm_from_config("memory", temperature=0.3)
        messages = [
            SystemMessage(content=_MEMORY_REPORT_PROMPT),
            HumanMessage(content=f"以下是用户的记忆数据：\n\n{memories_summary}"),
        ]
        report_result = await llm.ainvoke(messages)
        report_text = report_result.content
        if isinstance(report_text, list):
            report_text = "\n".join(
                (
                    str(item)
                    if isinstance(item, str)
                    else json.dumps(item, ensure_ascii=False)
                )
                for item in report_text
            )

        # 解析大模型返回的 JSON
        try:
            # 尝试提取 JSON 内容（兼容 markdown 代码块包裹）
            json_str = report_text
            if "```json" in json_str:
                json_str = json_str.split("```json", 1)[1].split("```", 1)[0]
            elif "```" in json_str:
                json_str = json_str.split("```", 1)[1].split("```", 1)[0]
            report_data = json.loads(json_str.strip())
        except (json.JSONDecodeError, IndexError) as e:
            logger.warning(f"[memory/report] JSON 解析失败，返回原始文本: {e}")
            report_data = {
                "basic_info": [],
                "attention_needed": [],
                "current_status": [],
                "recent_events": [],
                "preferences": [],
                "current_demands": [],
                "raw_text": report_text,
            }

        return NlResponse.success(
            content={"report": report_data, "memory_count": len(memories)}
        )

    except Exception as e:
        logger.error(f"[memory/report] 获取记忆失败: {e}", exc_info=True)
        return NlResponse.fail(
            content={}, message=f"获取记忆失败: {e}", status_code=500
        )
