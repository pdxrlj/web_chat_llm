"""
语音聊天管理路由。

提供 proxy 和 getScenes 两个接口，
与 JS 版 Server/app.js 的路由逻辑和响应格式完全一致。
"""

from pathlib import Path
from typing import Any

from fastapi import Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.http.handlers.base import router
from core.logger import setup_logger
from core.voice_server.voice_api import get_scenes, proxy_voice_api

logger = setup_logger("voice_mgr")

# 场景配置目录
SCENES_DIR = str(
    Path(__file__).parent.parent.parent.parent / "core" / "voice_server" / "scenes"
)


class ProxyRequest(BaseModel):
    """代理请求体。"""

    SceneID: str = Field(..., description="场景 ID")
    RoomId: str | None = Field(None, description="房间 ID，来自 getScenes 返回值")
    UserId: str | None = Field(None, description="用户 ID，来自 getScenes 返回值")
    AppId: str | None = Field(None, description="应用 ID，来自 getScenes 返回值")
    TaskId: str | None = Field(None, description="任务 ID，来自 StartVoiceChat 返回值")
    CustomLLMParams: dict[str, Any] | None = None
    CustomHeaders: dict[str, str] | None = None
    CustomSystemMessages: list[str] | None = None


class GetScenesRequest(BaseModel):
    """获取场景列表请求体。"""

    username: str | None = None


# ── 响应格式与 JS 版 wrapper 完全一致 ──────────────────────────────


def _success_response(
    api_name: str, result: Any, contain_response_metadata: bool = True
) -> JSONResponse:
    """成功响应，对应 JS 版 wrapper 的成功分支。"""
    if contain_response_metadata:
        return JSONResponse(
            {
                "ResponseMetadata": {"Action": api_name},
                "Result": result,
            }
        )
    else:
        # containResponseMetadata=false 时直接返回结果
        return JSONResponse(result)


def _error_response(api_name: str, message: str) -> JSONResponse:
    """错误响应，对应 JS 版 wrapper 的 catch 分支。"""
    return JSONResponse(
        {
            "ResponseMetadata": {
                "Action": api_name,
                "Error": {
                    "Code": -1,
                    "Message": message,
                },
            },
        }
    )


# ── 路由 ──────────────────────────────────────────────────────────


@router.post("/proxy")
async def proxy_handler(
    request: ProxyRequest,
    Action: str = Query(
        ..., description="OpenAPI Action，如 StartVoiceChat、StopVoiceChat"
    ),
    Version: str = Query("2024-12-01", description="OpenAPI Version"),
) -> JSONResponse:
    """
    代理火山 RTC AIGC OpenAPI 请求。

    与 JS 版一致：
    - POST /proxy?Action=xxx&Version=xxx
    - Body: { SceneID, CustomLLMParams?, CustomHeaders?, CustomSystemMessages? }
    - containResponseMetadata=false，直接返回火山 API 原始结果
    """

    # 完整输出请求信息
    logger.info(
        f"proxy 请求参数: Action={Action}, Version={Version}, "
        f"SceneID={request.SceneID}, AppId={request.AppId}, "
        f"RoomId={request.RoomId}, UserId={request.UserId}, TaskId={request.TaskId}, "
        f"CustomLLMParams={request.CustomLLMParams}, "
        f"CustomHeaders={request.CustomHeaders}, "
        f"CustomSystemMessages={request.CustomSystemMessages}"
    )

    try:
        result = await proxy_voice_api(
            action=Action,
            version=Version,
            scene_id=request.SceneID,
            request_body=request.model_dump(),
            scenes_dir=SCENES_DIR,
        )
        return _success_response("proxy", result, contain_response_metadata=False)
    except (ValueError, Exception) as e:
        logger.error(f"proxy 错误: {e}")
        return _error_response("proxy", str(e))


@router.post("/getScenes")
async def get_scenes_handler(request: GetScenesRequest) -> JSONResponse:
    """
    获取场景列表，并为每个场景生成 RTC Token。

    与 JS 版一致：
    - POST /getScenes
    - Body: { username? }
    - containResponseMetadata=true，返回 { ResponseMetadata, Result: { scenes } }
    """
    try:
        result = get_scenes(
            username=request.username,
            scenes_dir=SCENES_DIR,
        )
        return _success_response("getScenes", result)
    except (ValueError, Exception) as e:
        logger.error(f"getScenes 错误: {e}")
        return _error_response("getScenes", str(e))
