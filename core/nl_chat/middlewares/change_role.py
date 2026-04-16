import warnings
from copy import deepcopy
from pathlib import Path
from typing import Any

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field, SecretStr

from core.config import LLMConfig, config
from core.logger import setup_logger
from core.nl_chat.prompt_mgr import set_session_prompt
from core.voice_server.update_chat_config import update_voice_chat

logger = setup_logger("change_role_middleware")

SCENES_DIR = str(Path(__file__).parent.parent.parent / "voice_server" / "scenes")

ROLE_JUDGE_PROMPT = """你是一个角色意图识别器。根据用户输入，判断用户想切换到哪个角色。

可用角色列表：
{role_list}

判断规则：
1. 如果用户明确想切换到某个角色，返回该角色的名称（必须与列表中某个角色的名称完全一致）
2. 如果用户的表述与角色列表不匹配，返回空字符串

输出要求：
- 必须使用JSON格式返回
- 包含role_name字段，值为匹配到的角色名称（必须与列表中完全一致），未匹配则为空字符串
- 示例输出：{{"role_name": "健身教练"}}"""


class RoleJudgeResult(BaseModel):
    role_name: str = Field(description="匹配到的角色名称，未匹配则为空字符串")


# 角色切换意图的动词前缀（"换" 单字太短容易误触发，不使用）
_SWITCH_VERBS = ["切换", "切换到", "切换成", "换成", "变成"]


def _get_role_keywords() -> dict[str, list[str]]:
    """从场景配置中构建角色热词表。

    Returns:
        {角色名称: [热词列表]}，热词来源于 SceneConfig.name + 动词前缀组合
    """
    from core.voice_server.scene_loader import load_scenes

    scenes = load_scenes(SCENES_DIR)
    keywords: dict[str, list[str]] = {}
    for scene_id, scene_data in scenes.items():
        name = scene_data.get("SceneConfig", {}).get("name", "")
        if name:
            # 热词 = 角色名称本身 + scene_id + 动词前缀+角色名
            words = [name, scene_id]
            for verb in _SWITCH_VERBS:
                words.append(f"{verb}{name}")
            keywords[name] = words
    return keywords


# 热词表缓存，避免每次匹配都重新加载场景文件
_keywords_cache: dict[str, list[str]] | None = None


def _get_cached_role_keywords() -> dict[str, list[str]]:
    """获取缓存的角色热词表。"""
    global _keywords_cache
    if _keywords_cache is None:
        _keywords_cache = _get_role_keywords()
    return _keywords_cache


def _match_role_by_keyword(user_input: str) -> str | None:
    """用热词匹配用户输入中的角色切换意图。

    匹配规则：用户输入中同时包含切换动词 + 角色名称时才命中，
    避免用户只是在聊天中提到角色名称就误触发切换。

    Args:
        user_input: 用户输入文本

    Returns:
        匹配到的角色名称，未匹配返回 None
    """
    keywords = _get_cached_role_keywords()
    input_lower = user_input.lower()

    # 检查输入是否包含切换意图动词
    has_switch_intent = any(verb in input_lower for verb in _SWITCH_VERBS)
    if not has_switch_intent:
        return None

    # 在有切换意图的前提下，匹配角色名称（只匹配名称本身和 scene_id，跳过动词前缀组合）
    for role_name, words in keywords.items():
        # words[0] = 角色名称，words[1] = scene_id
        if words[0] and words[0] in input_lower:
            return role_name
        if words[1] and words[1].lower() in input_lower:
            return role_name

    return None


def _has_role_mention(user_input: str) -> bool:
    """检查用户输入中是否同时包含切换动词和角色名称。

    用于 LLM 调用前的快速过滤：如果连切换意图都不明显，
    就不需要浪费 LLM 调用来判断意图。

    Args:
        user_input: 用户输入文本

    Returns:
        是否有角色切换的可能意图
    """
    input_lower = user_input.lower()

    # 必须有切换动词
    if not any(verb in input_lower for verb in _SWITCH_VERBS):
        return False

    keywords = _get_cached_role_keywords()
    for role_name, words in keywords.items():
        # 只检查角色名称本身和 scene_id，不检查动词前缀组合
        if role_name and role_name in input_lower:
            return True
        if words[1] and words[1].lower() in input_lower:  # scene_id
            return True

    return False


def _get_role_list_text() -> str:
    """生成角色列表文本供 LLM prompt 使用。"""
    keywords = _get_cached_role_keywords()
    lines = []
    for role_name in keywords:
        lines.append(f"- {role_name}")
    return "\n".join(lines)


def _find_scene_by_name(role_name: str) -> tuple[str | None, dict[str, Any] | None]:
    """根据角色中文名称匹配场景配置。

    Args:
        role_name: 角色中文名称，如 "健身教练"

    Returns:
        (scene_id, scene_data) 元组，未找到则 (None, None)
    """
    from core.voice_server.scene_loader import load_scenes

    scenes = load_scenes(SCENES_DIR)
    role_lower = role_name.lower()

    # 1. 精确匹配 name
    for scene_id, scene_data in scenes.items():
        name = scene_data.get("SceneConfig", {}).get("name", "")
        if name and name == role_name:
            return scene_id, scene_data

    # 2. 精确匹配 scene_id
    for scene_id, scene_data in scenes.items():
        if scene_id.lower() == role_lower:
            return scene_id, scene_data

    # 3. 包含匹配 name（双向子串匹配）
    for scene_id, scene_data in scenes.items():
        name = scene_data.get("SceneConfig", {}).get("name", "")
        if name and (role_name in name or name in role_name):
            return scene_id, scene_data

    return None, None


class ChangeRoleMiddleware(AgentMiddleware):
    """中间件，在 Agent 执行前检测用户输入中的角色切换意图并自动切换。

    匹配策略：
    1. 热词匹配：用户输入包含角色名称（如"健身教练"）→ 直接切换
    2. LLM 判断：热词未命中时，用轻量模型判断用户意图 → 切换
    """

    def __init__(self, session_id: str | None = None):
        """
        Args:
            session_id: 会话 ID，优先从 AgentState 获取，此处作为备选传入
        """
        self.session_id = session_id
        self.judge_llm_config = config.get_llm("intention")
        if not self.judge_llm_config:
            logger.warning(
                "intention LLM 配置不存在，ChangeRoleMiddleware 将仅使用热词匹配（LLM 判断已禁用）"
            )
            self._llm_disabled = True
        else:
            self._llm_disabled = False

    def _judge_llm(self) -> ChatOpenAI:
        if not isinstance(self.judge_llm_config, LLMConfig):
            raise TypeError("intention LLM 配置类型错误")

        judge_config = {
            "model": self.judge_llm_config.model,
            "base_url": self.judge_llm_config.base_url,
            "temperature": 0.1,
            "extra_body": {"enable_thinking": False},
        }
        if self.judge_llm_config.api_key:
            judge_config["api_key"] = SecretStr(self.judge_llm_config.api_key)

        return ChatOpenAI(**judge_config)

    async def _judge_role_by_llm(self, user_input: str) -> str | None:
        """用 LLM 判断用户输入想切换到哪个角色。

        Args:
            user_input: 用户输入文本

        Returns:
            匹配到的角色名称，未匹配返回 None
        """
        try:
            prompt = ROLE_JUDGE_PROMPT.format(role_list=_get_role_list_text())
            messages = [
                SystemMessage(content=prompt),
                HumanMessage(content=user_input),
            ]

            llm = self._judge_llm()
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message=".*PydanticSerializationUnexpectedValue.*",
                    category=UserWarning,
                )
                struct_llm = llm.with_structured_output(RoleJudgeResult)
                response = await struct_llm.ainvoke(messages)

            if not isinstance(response, RoleJudgeResult):
                logger.warning(f"角色判断结果类型异常: {type(response)}")
                return None

            role_name = response.role_name.strip()
            if not role_name:
                return None

            logger.info(f"LLM 判断角色意图: {role_name}")
            return role_name

        except Exception as e:
            logger.error(f"LLM 角色判断失败: {e}", exc_info=True)
            return None

    async def _apply_role_change(self, session_id: str, role_name: str) -> bool:
        """执行角色切换。

        Args:
            session_id: 会话 ID
            role_name: 角色名称

        Returns:
            是否成功
        """
        scene_id, scene_data = _find_scene_by_name(role_name)
        if not scene_id or not scene_data:
            logger.warning(f"未找到角色: {role_name}")
            return False

        voice_chat_config = scene_data.get("VoiceChat", {}).get("Config", {})
        tts_config = deepcopy(voice_chat_config.get("TTSConfig", {}))
        llm_config = voice_chat_config.get("LLMConfig", {})

        # 提取系统提示词
        system_messages = llm_config.get("SystemMessages", [])
        system_prompt = system_messages[0] if system_messages else ""

        # 提取音色
        voice_type = (
            tts_config.get("ProviderParams", {}).get("audio", {}).get("voice_type", "")
        )

        logger.info(
            f"匹配到角色: role_name={role_name} -> scene_id={scene_id}, "
            f"voice_type={voice_type}"
        )

        # 更新本地会话的 system prompt
        if system_prompt:
            set_session_prompt(session_id, system_prompt)

        # 调用 UpdateVoiceChat 更新 RTC 配置
        # 注意：使用原始场景的 scene_id 签名，因为实际的 app_id/room_id/task_id
        # 属于原始场景，密钥必须与原始场景一致
        try:
            from core.voice_server import voice_api

            runtime = voice_api._runtime_state.get(session_id, {})
            original_scene_id = runtime.get("scene_id", scene_id)

            rtc_config: dict[str, Any] = {"TTSConfig": tts_config}
            if system_prompt:
                rtc_config["LLMConfig"] = {"SystemMessages": [system_prompt]}

            await update_voice_chat(
                scene_id=original_scene_id,
                request_body={
                    "SessionId": session_id,
                    "Command": "UpdateParameters",
                    "Parameters": {"Config": rtc_config},
                },
                scenes_dir=SCENES_DIR,
            )
            logger.info(
                f"角色切换成功: session={session_id}, "
                f"role={role_name}, scene_id={scene_id}, "
                f"voice_type={voice_type}"
            )
            return True
        except Exception as e:
            logger.error(f"角色切换失败: {e}", exc_info=True)
            return False

    async def abefore_agent(
        self, state: AgentState, runtime: Runtime
    ) -> dict[str, Any] | None:
        """Agent 执行前的钩子，检测用户输入中的角色切换意图。"""
        messages = state.get("messages", [])
        if not messages:
            return None

        # 取最后一条用户消息
        last_msg = messages[-1]
        if not isinstance(last_msg, HumanMessage):
            return None

        user_input = last_msg.content
        if not isinstance(user_input, str) or not user_input.strip():
            return None

        session_id = state.get("session_id") or self.session_id
        if not session_id:
            logger.warning("session_id 无法获取，跳过角色切换检测")
            return None

        # 1. 热词匹配（需要同时有切换动词 + 角色名称）
        role_name = _match_role_by_keyword(user_input)

        # 2. 热词未命中，且 LLM 可用时，检查是否提到了角色名称
        #    如果连角色名称都没提到，不需要调 LLM 浪费资源
        if not role_name and not self._llm_disabled and _has_role_mention(user_input):
            role_name = await self._judge_role_by_llm(user_input)

        if not role_name:
            return None

        # 3. 执行角色切换
        success = await self._apply_role_change(session_id, role_name)
        if success:
            # 切换成功，通过消息总线通知前端
            from core.nl_chat.middlewares.emotion_speculate import message_bus

            message_bus.send(
                "ChangeRoleMiddleware",
                message={
                    "type": "change_role",
                    "session_id": session_id,
                    "role_name": role_name,
                },
            )

        return None
