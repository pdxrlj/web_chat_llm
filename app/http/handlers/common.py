"""通用接口：场景列表、聊天分析报告查询。"""

from pathlib import Path
from typing import Any

from fastapi import Query

from app.http.handlers.base import router
from app.http.response import NlResponse
from core.logger import setup_logger
from core.model.chat_analyze_repo import get_chat_analyzes_by_session_id

logger = setup_logger("common")

SCENES_DIR = str(
    Path(__file__).parent.parent.parent.parent / "core" / "voice_server" / "scenes"
)


@router.get("/scenes")
async def list_scenes() -> NlResponse:
    """
    获取所有语音聊天场景列表。

    返回每个场景的 id、name、icon。
    """
    import commentjson

    scenes_path = Path(SCENES_DIR)
    result: list[dict[str, Any]] = []

    if not scenes_path.exists():
        return NlResponse.success(content={"scenes": result})

    for json_file in sorted(scenes_path.glob("*.json")):
        try:
            data = commentjson.loads(json_file.read_text(encoding="utf-8"))
            scene_config = data.get("SceneConfig", {})
            result.append(
                {
                    "scene_id": json_file.stem,
                    "name": scene_config.get("name", json_file.stem),
                    "icon": scene_config.get("icon", ""),
                }
            )
        except Exception as e:
            logger.error(f"读取场景配置失败 {json_file.name}: {e}")

    return NlResponse.success(content={"scenes": result})


@router.get("/chat_analyze")
async def get_chat_analyze(
    session_id: str = Query(..., description="会话ID"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
) -> NlResponse:
    """
    根据 session_id 获取聊天分析报告列表。
    """
    try:
        records = await get_chat_analyzes_by_session_id(
            session_id=session_id,
            page=page,
            page_size=page_size,
        )
        result = []
        for r in records:
            result.append(
                {
                    "id": r.id,
                    "session_id": r.session_id,
                    "role": r.role,
                    "report": r.report,
                    "created_at": (
                        r.created_at.isoformat() if r.created_at is not None else None
                    ),
                    "updated_at": (
                        r.updated_at.isoformat() if r.updated_at is not None else None
                    ),
                }
            )
        return NlResponse.success(
            content={"session_id": session_id, "records": result, "count": len(result)}
        )
    except Exception as e:
        logger.error(f"查询聊天分析报告失败: {e}")
        return NlResponse.fail(content={}, message=str(e), status_code=500)
