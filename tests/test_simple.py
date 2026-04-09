"""简单测试：添加和搜索记忆

运行方式:
  pytest tests/test_simple.py -v -s
  或
  python tests/test_simple.py
"""

import asyncio
import sys
import time

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
        flush_after=True,  # 添加后立即flush，确保测试中能搜索到
    )

    print(f"状态: {result['status']}")
    print(f"添加数量: {result['memories_added']}")
    print(f"记忆ID: {result['memory_ids']}")

    # 使用方法内部返回的时间信息，排除模型加载时间
    if "timing" in result:
        print(f"⏱️  提取记忆耗时: {result['timing']['extract']:.3f} 秒")
        print(f"⏱️  生成嵌入耗时: {result['timing']['embed']:.3f} 秒")
        print(f"⏱️  存储耗时: {result['timing']['conflict']:.3f} 秒")
        print(f"⏱️  方法总耗时: {result['timing']['total']:.3f} 秒")

    assert result["status"] == "success"
    return result.get("timing", {}).get("total", 0.0)


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

    # 使用方法内部返回的时间信息，排除模型加载时间
    if "timing" in result:
        print(f"⏱️  生成查询嵌入耗时: {result['timing']['embed']:.3f} 秒")
        print(f"⏱️  向量检索耗时: {result['timing']['search']:.3f} 秒")
        print(f"⏱️  结果格式化耗时: {result['timing']['format']:.3f} 秒")
        print(f"⏱️  方法总耗时: {result['timing']['total']:.3f} 秒")

    assert result["total"] >= 1
    return result.get("timing", {}).get("total", 0.0)


async def _test_conflict(mem):
    """测试添加冲突数据"""
    print("\n=== 测试添加冲突数据 ===")

    # 先添加一条初始记忆
    print("添加初始记忆: 我喜欢吃苹果")
    result1 = await mem.add(
        messages=[{"role": "user", "content": "我喜欢吃苹果"}],
        user_id=USER_ID,
        infer=True,
        auto_detect_conflict=False,
    )
    elapsed_time1 = result1.get("timing", {}).get("total", 0.0)
    print(f"⏱️  初始添加耗时: {elapsed_time1:.3f} 秒")
    if "timing" in result1:
        print(f"  - 提取记忆: {result1['timing']['extract']:.3f} 秒")
        print(f"  - 生成嵌入: {result1['timing']['embed']:.3f} 秒")
        print(f"  - 存储: {result1['timing']['conflict']:.3f} 秒")

    # 添加冲突记忆（相似内容）
    print("\n添加冲突记忆: 我喜欢吃香蕉（不应该冲突）")
    result2 = await mem.add(
        messages=[{"role": "user", "content": "我喜欢吃香蕉"}],
        user_id=USER_ID,
        infer=True,
        auto_detect_conflict=True,  # 启用冲突检测
    )
    elapsed_time2 = result2.get("timing", {}).get("total", 0.0)

    print(f"状态: {result2['status']}")
    print(f"添加数量: {result2['memories_added']}")
    print(f"检测到冲突: {len(result2.get('conflicts_detected', []))} 条")
    print(f"⏱️  冲突检测添加耗时: {elapsed_time2:.3f} 秒")
    if "timing" in result2:
        print(f"  - 提取记忆: {result2['timing']['extract']:.3f} 秒")
        print(f"  - 生成嵌入: {result2['timing']['embed']:.3f} 秒")
        print(f"  - 冲突检测和存储: {result2['timing']['conflict']:.3f} 秒")

    # 添加真正可能冲突的记忆
    print("\n添加真正冲突记忆: 我不喜欢吃苹果了，现在改吃橘子")
    result3 = await mem.add(
        messages=[{"role": "user", "content": "我不喜欢吃苹果了，现在改吃橘子"}],
        user_id=USER_ID,
        infer=True,
        auto_detect_conflict=True,
    )
    elapsed_time3 = result3.get("timing", {}).get("total", 0.0)

    print(f"状态: {result3['status']}")
    print(f"添加数量: {result3['memories_added']}")
    print(f"检测到冲突: {len(result3.get('conflicts_detected', []))} 条")
    if result3.get("conflicts_detected"):
        for conflict in result3["conflicts_detected"]:
            print(f"  - 冲突类型: {conflict['conflict_type']}")
            print(f"    旧记忆: {conflict['old_memory']['content']}")
            print(f"    新记忆: {conflict['new_memory']['content']}")
    print(f"⏱️  冲突检测添加耗时: {elapsed_time3:.3f} 秒")
    if "timing" in result3:
        print(f"  - 提取记忆: {result3['timing']['extract']:.3f} 秒")
        print(f"  - 生成嵌入: {result3['timing']['embed']:.3f} 秒")
        print(f"  - 冲突检测和存储: {result3['timing']['conflict']:.3f} 秒")

    assert result2["status"] == "success"
    assert result3["status"] == "success"
    return elapsed_time1, elapsed_time2, elapsed_time3


def main():
    """直接运行时的入口"""
    if sys.platform == "win32":
        import io

        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

    print("=" * 60)
    print("性能测试：添加 + 搜索 + 冲突检测 (Milvus)")
    print("=" * 60)

    # 创建客户端
    mem = asyncio.run(create_client())

    # 测试添加
    add_time = asyncio.run(_test_add(mem))

    # 测试搜索
    search_time = asyncio.run(_test_search(mem))

    # 测试冲突检测
    conflict_times = asyncio.run(_test_conflict(mem))

    print("\n" + "=" * 60)
    print("测试完成 - 性能汇总")
    print("=" * 60)
    print(f"📊 添加数据耗时: {add_time:.3f} 秒")
    print(f"📊 搜索数据耗时: {search_time:.3f} 秒")
    print(f"📊 初始添加耗时: {conflict_times[0]:.3f} 秒")
    print(f"📊 冲突检测添加耗时 (无冲突): {conflict_times[1]:.3f} 秒")
    print(f"📊 冲突检测添加耗时 (有冲突): {conflict_times[2]:.3f} 秒")
    print("=" * 60)


if __name__ == "__main__":
    main()
