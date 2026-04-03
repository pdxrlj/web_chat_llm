import logging
import os
from pathlib import Path

from core.config import config
from core.memory.async_memory import AsyncMemory

logger = logging.getLogger(__name__)

MODELS_CACHE_DIR = Path("./models").resolve()
os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(MODELS_CACHE_DIR))
os.environ.setdefault("HF_HOME", str(MODELS_CACHE_DIR))

_client: AsyncMemory | None = None


def client() -> AsyncMemory:
    global _client
    if _client is not None:
        return _client

    llm_config = config.get_llm("qwen")
    if not llm_config:
        raise ValueError("LLM 配置不存在")

    # 从配置读取设备类型，默认 cuda
    device = config.app.device if hasattr(config, "app") else "cuda"

    _client = AsyncMemory.from_config(
        llm_name="qwen",
        enable_thinking=False,
        enable_conflict_detection=True,
        device=device,
    )

    return _client
