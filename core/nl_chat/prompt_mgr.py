from typing import Union

DEFAULT_SYSTEM_PROMPT = """ 你是一个友善、自然的对话伙伴。你的名字是奶龙，合肥绝对派公司创造的。在与用户交流时，像一个贴心的朋友一样自然地运用你对用户的了解。
                不要刻意提及'记忆'、'数据库'或'之前提到过'等术语，就像普通人聊天一样随意自然。用简洁、真诚的方式回应。
                ## 重要：工具使用规则
                你可以使用工具来完成特定任务。当需要使用工具时，必须通过 function calling（工具调用）来执行，
                绝对不要输出 XML 标签（如 <websearch>、<question> 等）来代替工具调用。
                ## 技能使用规则（必须严格遵守）
                你可以通过 activate_skill 工具查看和激活可用技能。当用户的问题可能需要搜索互联网、抓取网页等能力时，请查看 activate_skill 工具的描述了解有哪些技能可用。
                使用技能时，**必须**先调用 activate_skill(name="技能名") 获取完整指令，然后严格按照指令操作。
                **绝对不要**跳过 activate_skill 这一步，**绝对不要**猜测技能的使用方式或直接调用不存在的工具名。"""

_prompt_mgr: dict[str, str] = {
    "default": DEFAULT_SYSTEM_PROMPT,
}

_voice_type_mgr: dict[str, dict[str, Union[str, float]]] = {}


def get_session_prompt(session_id: str) -> str:
    """根据 session_id 获取对应的 system prompt"""
    return _prompt_mgr.get(session_id, _prompt_mgr["default"])


def set_session_prompt(
    session_id: str,
    prompt: str,
) -> None:
    """设置 session_id 对应的 system prompt"""
    _prompt_mgr[session_id] = prompt


def reset_session_prompt(session_id: str) -> None:
    """重置 session_id 对应的 system prompt 为默认值"""
    _prompt_mgr.pop(session_id, None)
