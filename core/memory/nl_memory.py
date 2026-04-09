import logging
import os
from pathlib import Path

from core.config import MilvusStorageConfig, config
from core.memory.async_memory import AsyncMemory
from core.memory.async_memory.storage import MilvusStorage

logger = logging.getLogger(__name__)

MODELS_CACHE_DIR = Path("./models").resolve()
os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(MODELS_CACHE_DIR))
os.environ.setdefault("HF_HOME", str(MODELS_CACHE_DIR))

_client: AsyncMemory | None = None


def client() -> AsyncMemory:
    global _client
    if _client is not None:
        return _client

    llm_config = config.get_llm("memory")
    if not llm_config:
        raise ValueError("memory LLM 配置不存在")

    # 获取 Milvus 存储配置
    storage_config = config.get_storage("milvus")
    if not storage_config:
        raise ValueError("milvus 存储配置不存在")

    # 类型检查：确保是 MilvusStorageConfig
    if not isinstance(storage_config, MilvusStorageConfig):
        raise TypeError("存储配置类型错误，需要 MilvusStorageConfig")

    # 创建 MilvusStorage 实例
    storage = MilvusStorage(
        collection_name="async_memory",
        uri=storage_config.uri,
        token=storage_config.token,
        db_name=storage_config.db_name,
        embedding_dim=768,  # bge-base-en-v1.5 默认维度
    )

    # 从配置读取设备类型，默认 cuda
    device = config.app.device if hasattr(config, "app") else "cuda"

    _client = AsyncMemory.from_config(
        llm_name="memory",
        storage=storage,
        enable_thinking=False,
        enable_conflict_detection=True,
        similarity_threshold=0.6,  # 降低阈值，相似度>0.6即合并
        device=device,
    )

    return _client
