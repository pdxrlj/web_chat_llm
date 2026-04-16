"""中间件公共工具模块。

提供各中间件共用的常量、函数和工具类。
"""

from pathlib import Path

from blinker import signal
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from pydantic import SecretStr
from langchain_openai import ChatOpenAI

from core.config import LLMConfig, config
from core.logger import setup_logger

logger = setup_logger(__name__)

# 消息总线，供所有中间件共用
message_bus = signal("we_chat")

# 场景配置目录
SCENES_DIR = str(Path(__file__).parent.parent.parent / "voice_server" / "scenes")


def get_role_name(session_id: str) -> str:
    """根据 session_id 获取对应场景的角色名称。

    Args:
        session_id: 会话ID

    Returns:
        str: 角色名称，未找到时返回 "default"
    """
    try:
        from core.voice_server import voice_api
        from core.voice_server.scene_loader import load_scenes

        runtime = voice_api._runtime_state.get(session_id, {})
        scene_id = runtime.get("scene_id")
        if not scene_id:
            logger.debug(f"session {session_id} 未绑定语音会话，无法获取角色名称")
            return "default"

        scenes = load_scenes(SCENES_DIR)
        role_name = scenes.get(scene_id, {}).get("SceneConfig", {}).get("name", "")
        return role_name or scene_id
    except Exception as e:
        logger.warning(f"获取角色名称失败 (session: {session_id}): {e}")
    return "default"


def extract_message_content(msg: AnyMessage) -> str:
    """从消息中提取文本内容，处理 content 为字符串或列表的情况。

    Args:
        msg: LangChain 消息对象

    Returns:
        str: 消息文本内容
    """
    if isinstance(msg.content, str):
        return msg.content
    return str(msg.content)


def get_latest_human_message(messages: list[AnyMessage]) -> str | None:
    """从消息列表中获取最新的一条用户消息文本。

    Args:
        messages: 消息列表

    Returns:
        str | None: 用户消息文本，未找到返回 None
    """
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return extract_message_content(msg)
    return None


def get_latest_ai_message(messages: list[AnyMessage]) -> str | None:
    """从消息列表中获取最新的一条 AI 消息文本。

    Args:
        messages: 消息列表

    Returns:
        str | None: AI 消息文本，未找到返回 None
    """
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            return extract_message_content(msg)
    return None


def build_llm_from_config(llm_config_name: str, *, temperature: float = 0.7) -> ChatOpenAI:
    """根据配置名称构建 ChatOpenAI 实例。

    Args:
        llm_config_name: LLM 配置名称（对应 config.yaml 中的 key）
        temperature: 温度参数

    Returns:
        ChatOpenAI: 构建好的 LLM 实例

    Raises:
        ValueError: 配置不存在
        TypeError: 配置类型错误
    """
    llm_config = config.get_llm(llm_config_name)
    if not llm_config:
        raise ValueError(f"{llm_config_name} LLM 配置不存在")

    if not isinstance(llm_config, LLMConfig):
        raise TypeError(f"{llm_config_name} LLM 配置类型错误")

    chat_kwargs = {
        "model": llm_config.model,
        "base_url": llm_config.base_url,
        "temperature": temperature,
        "extra_body": {"enable_thinking": False},
    }

    if llm_config.api_key:
        chat_kwargs["api_key"] = SecretStr(llm_config.api_key)

    return ChatOpenAI(**chat_kwargs)
