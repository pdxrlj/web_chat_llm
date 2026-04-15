"""
场景配置文件加载器。

从 scenes 目录加载所有 JSON 场景配置文件，并从 config.yaml 注入 AccountConfig。
"""

import commentjson
from pathlib import Path
from typing import Any

from core.config import load_config
from core.logger import setup_logger

logger = setup_logger("voice_scene_loader")


def load_scenes(scenes_dir: str | Path) -> dict[str, dict[str, Any]]:
    """
    加载指定目录下的所有 .json 场景配置文件。

    从 config.yaml 的 voice 配置中读取 access_key_id 和 secret_key，
    注入到每个场景的 AccountConfig 中，避免在 JSON 文件中硬编码密钥。

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

    # 从 config.yaml 读取 voice 凭据
    cfg = load_config()
    account_config: dict[str, str] = {}
    if cfg.voice.access_key_id and cfg.voice.secret_key:
        account_config = {
            "accessKeyId": cfg.voice.access_key_id,
            "secretKey": cfg.voice.secret_key,
        }
    else:
        logger.warning("config.yaml 中 voice.access_key_id 或 voice.secret_key 未配置")

    for json_file in sorted(scenes_path.glob("*.json")):
        try:
            data = commentjson.loads(json_file.read_text(encoding="utf-8"))
            scene_id = json_file.stem
            # 用 config.yaml 中的凭据覆盖 JSON 中的 AccountConfig
            data["AccountConfig"] = account_config
            scenes[scene_id] = data
            logger.info(f"加载场景配置: {scene_id}")
        except Exception as e:
            logger.error(f"加载场景配置失败 {json_file.name}: {e}")

    return scenes
