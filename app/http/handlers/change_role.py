"""
角色变更接口。

用于更新会话的角色配置，包括系统提示词和语音音色。
"""

from pathlib import Path
from typing import Any
from fastapi import Request
from pydantic import BaseModel, Field, field_validator
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

    scene_id: str = Field(..., description="场景 ID，如 EnglishTutor、Custom")
    session_id: str = Field(..., description="会话 ID（UUID）")
    system_prompt: str = Field(..., description="系统提示词")
    app_id: str = Field(..., description="火山应用 AppId")
    room_id: str = Field(..., description="房间 ID")
    task_id: str | None = Field(None, description="任务 ID，不传则从运行时状态自动获取")
    voice_type: str = Field(..., description="音色 ID，如 BV002_streaming")
    speed_ratio: float = Field(1.0, description="语速，范围 [0.2, 3]")
    pitch_ratio: float = Field(1.0, description="音高，范围 [0.1, 3]")
    volume_ratio: float = Field(1.0, description="音量，范围 [0.1, 3]")

    @field_validator("system_prompt")
    @classmethod
    def validate_system_prompt(cls, v: str) -> str:
        """验证 system_prompt 不能为空"""
        if not v.strip():
            raise ValueError("system_prompt 不能为空")
        return v


@router.post("/change_role")
async def change_role(_req: Request, data: ChangeRoleRequest) -> NlResponse:
    """
    变更会话角色。

    同时更新：
    1. 会话的 system prompt
    2. TTS 音色配置（语速、音高、音量）
    """
    # 1. 设置会话的 system prompt
    set_session_prompt(data.session_id, data.system_prompt)

    # 2. 从场景配置中读取 TTS 原始配置，只更新需要变化的字段
    from core.voice_server.scene_loader import load_scenes

    scenes = load_scenes(SCENES_DIR)
    scene_data = scenes.get(data.scene_id)
    if not scene_data:
        return NlResponse(
            content={}, status_code=400, message=f"场景 {data.scene_id} 不存在"
        )

    original_tts: dict[str, Any] = (
        scene_data.get("VoiceChat", {}).get("Config", {}).get("TTSConfig", {})
    )
    tts_config: dict[str, Any] = dict(original_tts)
    # 仅覆盖音色和音频参数
    if "ProviderParams" not in tts_config:
        tts_config["ProviderParams"] = {}
    if "app" not in tts_config["ProviderParams"]:
        tts_config["ProviderParams"]["app"] = {}
    if "audio" not in tts_config["ProviderParams"]:
        tts_config["ProviderParams"]["audio"] = {}
    tts_config["ProviderParams"]["audio"].update(
        {
            "voice_type": data.voice_type,
            "speed_ratio": data.speed_ratio,
            "pitch_ratio": data.pitch_ratio,
            "volume_ratio": data.volume_ratio,
        }
    )

    # 3. 调用 UpdateVoiceChat 更新音色配置
    request_body: dict[str, Any] = {
        "AppId": data.app_id,
        "RoomId": data.room_id,
        "Command": "UpdateParameters",
        "Parameters": {
            "Config": {
                "TTSConfig": tts_config,
            }
        },
    }
    if data.task_id:
        request_body["TaskId"] = data.task_id

    await update_voice_chat(
        scene_id=data.scene_id,
        request_body=request_body,
        scenes_dir=SCENES_DIR,
    )

    return NlResponse(content={}, status_code=200, message="角色变更成功")
