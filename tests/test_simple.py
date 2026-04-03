"""简单测试：添加和搜索记忆

运行方式:
  pytest tests/test_simple.py -v -s
  或
  python tests/test_simple.py
"""

import asyncio
import sys

from core.config import config as app_config

USER_ID = "test_simple_user"


async def create_client():
    """创建 Milvus 客户端"""
    from core.memory.async_memory.memory import AsyncMemory
    from core.memory.async_memory.storage import MilvusStorage

    milvus_cfg = app_config.get_storage("milvus")
    if not milvus_cfg:
        raise RuntimeError("未配置 Milvus")
    assert milvus_cfg.name == "milvus"

    storage = MilvusStorage(
        collection_name="test_simple",
        uri=milvus_cfg.uri,
        token=milvus_cfg.token,
        db_name=milvus_cfg.db_name,
        embedding_dim=768,
    )
    await storage._connect()
    assert storage._client is not None
    if storage._client.has_collection(storage.collection_name):
        storage._client.drop_collection(storage.collection_name)
    # 断开连接，下次 add/search 时会自动重建 collection
    storage._client = None

    device = app_config.app.device
    print(f"设备: {device}")
    return AsyncMemory.from_config("qwen", storage=storage, device=device)


async def _test_add(mem):
    """测试添加一条记忆"""
    print("\n=== 测试添加单条记忆 ===")
    result = await mem.add(
        messages=[{"role": "user", "content": "我喜欢吃苹果"}],
        user_id=USER_ID,
        infer=True,
        auto_detect_conflict=False,
    )

    print(f"状态: {result['status']}")
    print(f"添加数量: {result['memories_added']}")
    print(f"记忆ID: {result['memory_ids']}")
    
    assert result["status"] == "success"


async def _test_search(mem):
    """测试搜索记忆"""
    print("\n=== 测试搜索记忆 ===")

    result = await mem.search(
        query="水果偏好",
        user_id=USER_ID,
        top_k=5,
        use_reranker=False,
    )

    print(f"搜索结果数: {result['total']}")
    for r in result["results"]:
        print(f"  - [{r['score']:.4f}] {r['content']}")
    
    assert result["total"] >= 1


def main():
    """直接运行时的入口"""
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

    print("=" * 60)
    print("简单测试：添加 + 搜索 (Milvus)")
    print("=" * 60)

    # 创建客户端
    mem = asyncio.run(create_client())

    # 测试添加
    asyncio.run(_test_add(mem))

    # 测试搜索
    asyncio.run(_test_search(mem))

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
