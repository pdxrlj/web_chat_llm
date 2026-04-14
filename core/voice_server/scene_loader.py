"""
场景配置文件加载器。

从 scenes 目录加载所有 JSON 场景配置文件。
"""

import json
from pathlib import Path
from typing import Any

from core.logger import setup_logger

logger = setup_logger("voice_scene_loader")


def load_scenes(scenes_dir: str | Path) -> dict[str, dict[str, Any]]:
    """
    加载指定目录下的所有 .json 场景配置文件。

    Args:
        scenes_dir: 场景 JSON 文件所在目录路径

    Returns:
        以文件名（去掉 .json 后缀）为 key 的场景字典
    """
    scenes: dict[str, dict[str, Any]] = {}
    scenes_path = Path(scenes_dir)

    if not scenes_path.exists():
        logger.warning(f"场景目录不存在: {scenes_path}")
        return scenes

    for json_file in sorted(scenes_path.glob("*.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            scene_id = json_file.stem
            scenes[scene_id] = data
            logger.info(f"加载场景配置: {scene_id}")
        except Exception as e:
            logger.error(f"加载场景配置失败 {json_file.name}: {e}")

    return scenes
