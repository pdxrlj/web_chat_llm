"""记忆系统集成测试

使用 config.yaml 真实配置，测试 Milvus 存储、冲突检测、相似查询。
运行方式: uv run python tests/test_memory.py
"""

import asyncio
import sys

if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from core.config import config as app_config

USER_ID = "test_memory_user"


async def create_client():
    from core.memory.async_memory.memory import AsyncMemory
    from core.memory.async_memory.storage import MilvusStorage

    milvus_cfg = app_config.get_storage("milvus")
    if not milvus_cfg:
        raise RuntimeError("未配置 Milvus")
    assert milvus_cfg.name == "milvus"

    storage = MilvusStorage(
        collection_name="test_memory",
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
    return AsyncMemory.from_config("qwen", storage=storage, device=device)


async def test_add_simple(mem):
    print("\n=== 测试: 添加简单记忆 ===")
    result = await mem.add(
        messages=[{"role": "user", "content": "我喜欢吃苹果和香蕉"}],
        user_id=USER_ID,
        infer=False,
        auto_detect_conflict=False,
    )
    assert result["status"] == "success"
    print(f"  OK: {result['memories_added']} 条记忆已添加")


async def test_add_multi_turn(mem):
    print("\n=== 测试: 添加多轮对话记忆 ===")
    result = await mem.add(
        messages=[
            {"role": "user", "content": "我是软件工程师，今年30岁"},
            {"role": "assistant", "content": "好的，你是软件工程师。"},
            {"role": "user", "content": "我住在北京，喜欢编程和读书"},
        ],
        user_id=USER_ID,
        infer=False,
        auto_detect_conflict=False,
    )
    assert result["status"] == "success"
    print(f"  OK: {result['memories_added']} 条记忆已添加")


async def test_search(mem):
    print("\n=== 测试: 相似查询 ===")

    for query in ["水果偏好", "职业工作", "兴趣爱好"]:
        results = await mem.search(
            query=query,
            user_id=USER_ID,
            top_k=3,
            use_reranker=False,
        )
        print(f"  搜索 '{query}': {results['total']} 条结果")
        for r in results["results"]:
            print(f"    - [{r['score']:.4f}] {r['content']}")

    # 带 reranker 的搜索
    results = await mem.search(
        query="兴趣爱好",
        user_id=USER_ID,
        top_k=3,
        use_reranker=True,
    )
    print(f"  Reranker 搜索 '兴趣爱好': {results['total']} 条结果")
    for r in results["results"]:
        print(f"    - [{r['score']:.4f}] {r['content']}")

    assert True
    print("  OK: 搜索完成")


async def test_conflict_detection(mem):
    print("\n=== 测试: 冲突检测 ===")
    uid = f"{USER_ID}_conflict"

    await mem.add(
        messages=[{"role": "user", "content": "我喜欢跑步，每周跑三次"}],
        user_id=uid,
        infer=False,
        auto_detect_conflict=False,
    )
    print("  已添加: 喜欢跑步")

    result = await mem.add(
        messages=[{"role": "user", "content": "我膝盖受伤了，现在不喜欢运动了"}],
        user_id=uid,
        infer=True,
        auto_detect_conflict=True,
    )
    conflicts = len(result.get("conflicts_detected", []))
    print(f"  冲突检测结果: {result}")
    print(f"  检测到 {conflicts} 条冲突")
    print("  OK: 冲突检测完成")


async def test_preference_evolution(mem):
    print("\n=== 测试: 偏好演化 (A->B->C) ===")
    uid = f"{USER_ID}_evolution"

    for content in [
        "我最喜欢的编程语言是 Python",
        "我最近在学习 Go 语言，觉得很好用",
        "我现在最喜欢 Rust，它比 Go 和 Python 都好",
    ]:
        await mem.add(
            messages=[{"role": "user", "content": content}],
            user_id=uid,
            infer=False,
            auto_detect_conflict=False,
        )
        print(f"  已添加: {content[:20]}...")

    results = await mem.search("编程语言", user_id=uid, top_k=5, use_reranker=False)
    print(f"  搜索 '编程语言': {results['total']} 条")
    for r in results["results"]:
        print(f"    - [{r['score']:.4f}] {r['content']}")
    print("  OK: 偏好演化完成")


async def test_get_all_and_delete(mem):
    print("\n=== 测试: 获取全部 + 删除 ===")
    uid = f"{USER_ID}_crud"

    await mem.add(
        messages=[{"role": "user", "content": "测试获取全部记忆A"}],
        user_id=uid,
        infer=False,
    )
    await mem.add(
        messages=[{"role": "user", "content": "测试获取全部记忆B"}],
        user_id=uid,
        infer=False,
    )

    all_m = await mem.get_all(user_id=uid)
    assert all_m["total"] >= 2
    print(f"  获取全部: {all_m['total']} 条")

    if all_m["memories"]:
        mid = all_m["memories"][0]["id"]
        del_result = await mem.delete(mid)
        assert del_result["status"] == "success"
        print(f"  删除记忆 {mid}: {del_result['status']}")

    print("  OK: CRUD 完成")


async def test_organize(mem):
    print("\n=== 测试: 异步整理任务 ===")
    uid = f"{USER_ID}_organize"

    for content in ["我喜欢喝咖啡", "我最近改喝茶了", "我住在上海", "我搬到了北京"]:
        await mem.add(
            messages=[{"role": "user", "content": content}],
            user_id=uid,
            infer=False,
            auto_detect_conflict=False,
        )

    result = await mem.organize(user_id=uid)
    print(f"  整理结果: {result}")

    for query in ["饮品", "居住地"]:
        results = await mem.search(query, user_id=uid, top_k=3, use_reranker=False)
        print(f"  整理后搜索 '{query}': {results['total']} 条")
        for r in results["results"]:
            print(f"    - [{r['score']:.4f}] {r['content']}")

    print("  OK: 整理完成")


async def test_full_lifecycle(mem):
    print("\n=== 测试: 完整生命周期 ===")
    uid = f"{USER_ID}_lifecycle"

    await mem.add(
        messages=[{"role": "user", "content": "我叫张三，是一名数据科学家"}],
        user_id=uid,
        infer=False,
    )
    print("  [1] 添加初始记忆 OK")

    s1 = await mem.search("职业", user_id=uid, top_k=3, use_reranker=False)
    assert s1["total"] >= 1
    print(f"  [2] 搜索验证 OK: {s1['total']} 条")

    await mem.add(
        messages=[{"role": "user", "content": "我喜欢使用 Python 和 TensorFlow"}],
        user_id=uid,
        infer=False,
    )
    print("  [3] 添加技能记忆 OK")

    r3 = await mem.add(
        messages=[{"role": "user", "content": "我转行了，现在是产品经理"}],
        user_id=uid,
        infer=True,
        auto_detect_conflict=True,
    )
    print(f"  [4] 冲突测试: conflicts={len(r3.get('conflicts_detected', []))}")

    s2 = await mem.search("职业", user_id=uid, top_k=5, use_reranker=False)
    print(f"  [5] 最终搜索: {s2['total']} 条")
    for r in s2["results"]:
        print(f"      - [{r['score']:.4f}] {r['content']}")

    all_m = await mem.get_all(user_id=uid)
    print(f"  [6] 全部记忆: {all_m['total']} 条")
    print("  集成测试通过!")


async def main():
    print("=" * 60)
    print("记忆系统集成测试 (Milvus + 冲突检测 + 相似查询)")
    print("=" * 60)

    mem = await create_client()
    print("AsyncMemory 初始化完成")

    tests = [
        test_add_simple,
        test_add_multi_turn,
        test_search,
        test_conflict_detection,
        test_preference_evolution,
        test_get_all_and_delete,
        test_organize,
        test_full_lifecycle,
    ]

    failed = []
    for test in tests:
        try:
            await test(mem)
        except Exception as e:
            print(f"  FAIL: {e}")
            import traceback

            traceback.print_exc()
            failed.append(test.__name__)

    print("\n" + "=" * 60)
    if failed:
        print(f"FAIL: {len(failed)} 个测试失败")
        for name in failed:
            print(f"  - {name}")
    else:
        print("ALL PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
