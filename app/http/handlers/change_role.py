"""
角色变更接口。

用于更新会话的语音音色和系统提示词配置。
"""

from copy import deepcopy
from pathlib import Path
from typing import Any

from fastapi import Request
from pydantic import BaseModel, Field

from app.http.handlers.base import router
from app.http.response import NlResponse
from core.nl_chat.prompt_mgr import set_session_prompt
from core.voice_server.update_chat_config import update_voice_chat

# 场景配置目录
SCENES_DIR = str(
    Path(__file__).parent.parent.parent.parent / "core" / "voice_server" / "scenes"
)


class ChangeRoleRequest(BaseModel):
    """角色变更请求。"""

    session_id: str = Field(..., description="会话 ID（UUID），用于定位运行时状态")
    voice_type: str = Field(
        ..., description="音色 ID，如 zh_female_wanqudashu_moon_bigtts"
    )
    scene_id: str | None = Field(
        None, description="场景 ID，不传则从运行时状态自动获取"
    )
    system_prompt: str | None = Field(None, description="系统提示词，不传则保持原值")
    speed_ratio: float | None = Field(
        None, description="语速，范围 [0.2, 3]，不传则保持原值"
    )
    pitch_ratio: float | None = Field(
        None, description="音高，范围 [0.1, 3]，不传则保持原值"
    )
    volume_ratio: float | None = Field(
        None, description="音量，范围 [0.1, 3]，不传则保持原值"
    )


@router.post("/change_role")
async def change_role(_req: Request, data: ChangeRoleRequest) -> NlResponse:
    """
    变更会话角色（TTS 音色 + 系统提示词）。

    只需传 session_id 和 voice_type，其余参数从运行时状态和场景配置自动获取。
    传入 system_prompt 可同时更新 LLM 的系统提示词。
    """
    # 1. 从运行时状态获取 scene_id（如未传）
    from core.voice_server import voice_api

    runtime = voice_api._runtime_state.get(data.session_id)
    scene_id = data.scene_id or (runtime.get("scene_id") if runtime else None)
    if not scene_id:
        return NlResponse(
            content={},
            status_code=400,
            message="scene_id 无法获取，请先启动语音会话或显式传入",
        )

    # 2. 更新本地会话的 system prompt
    if data.system_prompt:
        set_session_prompt(data.session_id, data.system_prompt)

    # 3. 从场景配置中读取 TTS 原始配置
    from core.voice_server.scene_loader import load_scenes

    scenes = load_scenes(SCENES_DIR)
    scene_data = scenes.get(scene_id)
    if not scene_data:
        return NlResponse(
            content={}, status_code=400, message=f"场景 {scene_id} 不存在"
        )

    # 深拷贝避免污染缓存
    tts_config: dict[str, Any] = deepcopy(
        scene_data.get("VoiceChat", {}).get("Config", {}).get("TTSConfig", {})
    )
    if "ProviderParams" not in tts_config:
        tts_config["ProviderParams"] = {}
    if "audio" not in tts_config["ProviderParams"]:
        tts_config["ProviderParams"]["audio"] = {}

    # 覆盖传入的参数
    audio = tts_config["ProviderParams"]["audio"]
    audio["voice_type"] = data.voice_type
    if data.speed_ratio is not None:
        audio["speed_ratio"] = data.speed_ratio
    if data.pitch_ratio is not None:
        audio["pitch_ratio"] = data.pitch_ratio
    if data.volume_ratio is not None:
        audio["volume_ratio"] = data.volume_ratio

    # 4. 构建 Parameters.Config
    config: dict[str, Any] = {"TTSConfig": tts_config}
    if data.system_prompt:
        config["LLMConfig"] = {"SystemMessages": [data.system_prompt]}

    # 5. 调用 UpdateVoiceChat，通过 session_id 自动获取 AppId/RoomId/TaskId
    await update_voice_chat(
        scene_id=scene_id,
        request_body={
            "SessionId": data.session_id,
            "Command": "UpdateParameters",
            "Parameters": {"Config": config},
        },
        scenes_dir=SCENES_DIR,
    )

    return NlResponse(content={}, status_code=200, message="角色变更成功")
