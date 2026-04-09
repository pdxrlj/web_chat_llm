"""存储抽象层"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .models import MemoryItem

logger = logging.getLogger(__name__)


class BaseStorage(ABC):
    """存储抽象基类"""

    async def _connect(self):
        """延迟连接到存储系统（子类实现）"""
        pass

    @abstractmethod
    async def flush(self):
        """刷新缓冲区，确保数据持久化"""
        pass

    @abstractmethod
    async def add(self, memory: MemoryItem) -> bool:
        """添加记忆"""
        pass

    @abstractmethod
    async def get(self, memory_id: str) -> Optional[MemoryItem]:
        """获取单个记忆"""
        pass

    @abstractmethod
    async def update(self, memory: MemoryItem) -> bool:
        """更新记忆"""
        pass

    @abstractmethod
    async def delete(self, memory_id: str) -> bool:
        """删除记忆"""
        pass

    @abstractmethod
    async def search_by_embedding(
        self,
        embedding: List[float],
        top_k: int = 10,
        user_id: Optional[str] = None,
    ) -> List[tuple[MemoryItem, float]]:
        """向量检索，返回 (记忆, 相似度) 列表"""
        pass

    @abstractmethod
    async def search_by_metadata(
        self,
        filters: Dict[str, Any],
        limit: int = 100,
    ) -> List[MemoryItem]:
        """元数据检索"""
        pass

    @abstractmethod
    async def get_all(
        self,
        user_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[MemoryItem]:
        """获取所有记忆"""
        pass


class MilvusStorage(BaseStorage):
    """Milvus 向量数据库存储"""

    def __init__(
        self,
        collection_name: str = "async_memory",
        uri: str = "http://localhost:19530",
        token: Optional[str] = None,
        db_name: str = "default",
        embedding_dim: int = 768,
    ):
        self.collection_name = collection_name
        self.uri = uri
        self.token = token
        self.db_name = db_name
        self.embedding_dim = embedding_dim

        self._client: Optional[Any] = None
        self._collection = None

    async def _connect(self):
        """延迟连接"""
        if self._client is None:
            from pymilvus import MilvusClient, CollectionSchema, FieldSchema, DataType

            client = MilvusClient(
                uri=self.uri,
                token=self.token or "",
                db_name=self.db_name,
            )
            self._client = client

            # 创建集合（如果不存在）— 使用显式 schema 以支持 string id
            if not client.has_collection(self.collection_name):
                fields = [
                    FieldSchema(
                        name="id",
                        dtype=DataType.VARCHAR,
                        is_primary=True,
                        max_length=64,
                    ),
                    FieldSchema(
                        name="vector",
                        dtype=DataType.FLOAT_VECTOR,
                        dim=self.embedding_dim,
                    ),
                    FieldSchema(
                        name="content", dtype=DataType.VARCHAR, max_length=2048
                    ),
                    FieldSchema(name="user_id", dtype=DataType.VARCHAR, max_length=128),
                    FieldSchema(
                        name="memory_type", dtype=DataType.VARCHAR, max_length=32
                    ),
                    FieldSchema(
                        name="created_at", dtype=DataType.VARCHAR, max_length=32
                    ),
                    FieldSchema(
                        name="metadata", dtype=DataType.VARCHAR, max_length=4096
                    ),
                ]
                schema = CollectionSchema(fields=fields, description="Memory storage")
                client.create_collection(
                    collection_name=self.collection_name,
                    schema=schema,
                )
                # 创建向量索引（load 需要）
                index_params = client.prepare_index_params()
                index_params.add_index(
                    field_name="vector",
                    index_type="IVF_FLAT",
                    metric_type="COSINE",
                    params={"nlist": 128},
                )
                client.create_index(
                    collection_name=self.collection_name,
                    index_params=index_params,
                )
            # 确保 collection 已加载（query/search 需要）
            client.load_collection(self.collection_name)

    async def flush(self):
        """刷新缓冲区，确保数据持久化到存储"""
        if self._client is not None:
            self._client.flush(self.collection_name)

    async def add(self, memory: MemoryItem) -> bool:
        await self._connect()

        if not memory.embedding:
            logger.warning(f"记忆 {memory.id} 缺少嵌入向量")
            return False

        data = {
            "id": memory.id,
            "vector": memory.embedding,
            "content": memory.content,
            "user_id": memory.user_id or "",
            "memory_type": memory.memory_type.value,
            "created_at": memory.created_at.isoformat(),
            "metadata": str(memory.metadata),
        }

        assert self._client is not None  # 类型断言
        self._client.insert(
            collection_name=self.collection_name,
            data=[data],
        )
        # 移除每次插入都调用flush的操作，改为定期flush或批量操作
        # 这样可以显著提高插入性能
        # self._client.flush(self.collection_name)

        return True

    async def get(self, memory_id: str) -> Optional[MemoryItem]:
        await self._connect()

        assert self._client is not None  # 类型断言
        results = self._client.get(
            collection_name=self.collection_name,
            ids=[memory_id],
        )

        if not results:
            return None

        data = results[0]
        return self._data_to_memory(data)

    async def update(self, memory: MemoryItem) -> bool:
        """Milvus 不支持原地更新，需要先删除再插入"""
        await self.delete(memory.id)
        return await self.add(memory)

    async def delete(self, memory_id: str) -> bool:
        await self._connect()

        assert self._client is not None  # 类型断言
        self._client.delete(
            collection_name=self.collection_name,
            ids=[memory_id],
        )
        self._client.flush(self.collection_name)

        return True

    async def search_by_embedding(
        self,
        embedding: List[float],
        top_k: int = 10,
        user_id: Optional[str] = None,
    ) -> List[tuple[MemoryItem, float]]:
        await self._connect()

        # 移除搜索前的强制flush，提高搜索性能
        # 数据会由Milvus自动异步flush到磁盘，保持最终一致性
        # 如果需要强一致性，可以在插入后手动调用flush

        filter_expr = None
        if user_id:
            filter_expr = f'user_id == "{user_id}"'

        assert self._client is not None  # 类型断言
        # 使用更高的nprobe值提高搜索召回率
        results = self._client.search(
            collection_name=self.collection_name,
            data=[embedding],
            limit=top_k,
            filter=filter_expr or "",
            output_fields=[
                "id",
                "content",
                "user_id",
                "memory_type",
                "created_at",
                "metadata",
            ],
            search_params={"metric_type": "COSINE", "params": {"nprobe": 100}},
        )

        memories_with_scores = []
        for hits in results:
            for hit in hits:
                memory = self._data_to_memory(hit["entity"])
                score = hit["distance"]
                memories_with_scores.append((memory, score))

        return memories_with_scores

    async def search_by_metadata(
        self,
        filters: Dict[str, Any],
        limit: int = 100,
    ) -> List[MemoryItem]:
        """元数据检索（使用标量过滤）"""
        await self._connect()

        # 构建 Milvus 过滤表达式
        filter_parts = []
        for key, value in filters.items():
            if isinstance(value, str):
                filter_parts.append(f'{key} == "{value}"')
            else:
                filter_parts.append(f"{key} == {value}")

        filter_expr = " and ".join(filter_parts) if filter_parts else None

        # 使用查询而非搜索（不需要向量）
        # 注意：Milvus 的标量查询功能有限
        assert self._client is not None  # 类型断言
        results = self._client.query(
            collection_name=self.collection_name,
            filter=filter_expr or "",
            limit=limit,
            output_fields=[
                "id",
                "content",
                "user_id",
                "memory_type",
                "created_at",
                "metadata",
            ],
        )

        return [self._data_to_memory(data) for data in results]

    async def get_all(
        self,
        user_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[MemoryItem]:
        await self._connect()

        filter_expr = None
        if user_id:
            filter_expr = f'user_id == "{user_id}"'

        assert self._client is not None  # 类型断言
        results = self._client.query(
            collection_name=self.collection_name,
            filter=filter_expr or "",
            limit=limit,
            output_fields=[
                "id",
                "content",
                "user_id",
                "memory_type",
                "created_at",
                "metadata",
            ],
        )

        return [self._data_to_memory(data) for data in results]

    def _data_to_memory(self, data: Dict[str, Any]) -> MemoryItem:
        """将 Milvus 数据转换为 MemoryItem"""
        import json

        from .models import MemoryType

        memory_type_str = data.get("memory_type", "fact")
        memory_type = (
            MemoryType(memory_type_str)
            if isinstance(memory_type_str, str)
            else memory_type_str
        )

        return MemoryItem(
            id=data["id"],
            content=data["content"],
            memory_type=memory_type,
            user_id=data.get("user_id") or None,
            created_at=datetime.fromisoformat(data["created_at"]),
            metadata=json.loads(data.get("metadata", "{}")),
        )
