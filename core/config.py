import os
from typing import Literal, cast

import yaml
from pydantic import BaseModel, Field


class AppConfig(BaseModel):
    """应用配置"""

    port: int = 8000
    log_level: str = "INFO"
    device: str = "cuda"  # cuda 或 cpu


class VoiceConfig(BaseModel):
    """火山语音 RTC 配置"""

    access_key_id: str = ""
    secret_key: str = ""


class LLMConfig(BaseModel):
    """LLM 模型配置"""

    name: str
    model: str
    model_provider: str
    base_url: str
    api_key: str = ""


class EmbeddingConfig(BaseModel):
    """Embedding 模型配置"""

    name: str
    model: str
    model_provider: str
    base_url: str = ""  # 本地模型不需要 base_url
    api_key: str = ""


class MilvusStorageConfig(BaseModel):
    """Milvus 向量数据库配置"""

    name: Literal["milvus"]
    uri: str
    token: str
    db_name: str
    chat_record_collection_name_prefix: str
    user_profile_collection_name: str


class PostgresStorageConfig(BaseModel):
    """PostgreSQL 数据库配置"""

    name: Literal["postgres"]
    host: str
    port: int
    user: str
    password: str
    db_name: str


class RedisStorageConfig(BaseModel):
    """Redis 缓存配置"""

    name: Literal["redis"]
    host: str
    port: int
    username: str = ""
    password: str = ""


# 存储配置联合类型
StorageConfig = MilvusStorageConfig | PostgresStorageConfig | RedisStorageConfig


class Config(BaseModel):
    """主配置类"""

    app: AppConfig = Field(default_factory=AppConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    llm: list[LLMConfig] = Field(default_factory=list)
    embedding: list[EmbeddingConfig] = Field(default_factory=list)
    storage: list[StorageConfig] = Field(default_factory=list)

    def get_llm(self, name: str) -> LLMConfig | None:
        """根据名称获取 LLM 配置"""
        for llm in self.llm:
            if llm.name == name:
                return llm
        return None

    def get_embedding(self, name: str) -> EmbeddingConfig | None:
        """根据名称获取 Embedding 配置"""
        for embedding in self.embedding:
            if embedding.name == name:
                return embedding
        return None

    def get_storage(self, name: str) -> StorageConfig | None:
        """根据名称获取存储配置"""
        for storage in self.storage:
            if storage.name == name:
                return storage
        return None


# 配置文件优先级（按顺序合并，后面的覆盖前面的）
_CONFIG_FILES = [
    "config.yaml",
    "config.local.yaml",
    "config.prod.yaml",
    "config.test.yaml",
]

# 全局配置缓存
_config: Config | None = None


def load_config(reload: bool = False) -> Config:
    """加载配置（单例模式）

    Args:
        reload: 是否强制重新加载

    Returns:
        Config: 配置对象
    """
    global _config

    if _config is not None and not reload:
        return _config

    merged_data: dict[str, object] = {}

    for config_file in _CONFIG_FILES:
        if not os.path.exists(config_file):
            continue
        with open(config_file, "r", encoding="utf-8") as f:
            raw_data: object = yaml.safe_load(f) or {}
            if isinstance(raw_data, dict):
                config_data = cast(dict[str, object], raw_data)
                _deep_merge(merged_data, config_data)

    _config = Config.model_validate(merged_data)
    return _config


def _deep_merge(base: dict[str, object], override: dict[str, object]) -> None:
    """深度合并两个字典"""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            child_base = cast(dict[str, object], base[key])
            child_override = cast(dict[str, object], value)
            _deep_merge(child_base, child_override)
        else:
            base[key] = value


# 模块加载时自动初始化配置
config = load_config()
