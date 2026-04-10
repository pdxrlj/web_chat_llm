"""Quick test script for conflict detection"""
import asyncio
import sys
import os

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def main():
    from core.memory.nl_memory import client as get_client

    memory = get_client()
    await memory.warm_up(load_embedding=True, load_reranker_model=False)

    # Clean
    all_m = await memory.get_all(user_id="test_user", limit=100)
    for m in all_m["memories"]:
        await memory.delete(m["id"])
    await memory.storage._connect()
    await memory.storage.flush()

    # Step 1: Add 'like'
    r1 = await memory.add(
        messages=[{"role": "user", "content": "我很喜欢吃苹果，每天都要吃一个"}],
        user_id="test_user",
        session_id="s1",
        flush_after=True,
    )
    print(f"Step1: extracted={r1['memories_extracted']}, added={r1['memories_added']}, conflicts={r1['conflicts_detected']}")

    m1 = await memory.get_all(user_id="test_user", limit=10)
    print(f"After step 1: {m1['total']} records")
    for x in m1["memories"]:
        print(f"  [{x['id'][:12]}] {x['content']}")

    # Step 2: Add conflict 'dislike'
    r2 = await memory.add(
        messages=[{"role": "user", "content": "其实我最近不喜欢吃苹果了，感觉太甜了"}],
        user_id="test_user",
        session_id="s2",
        flush_after=True,
    )
    print(f"Step2: extracted={r2['memories_extracted']}, added={r2['memories_added']}, conflicts={r2['conflicts_detected']}")

    mf = await memory.get_all(user_id="test_user", limit=10)
    print(f"Final: {mf['total']} records")
    for x in mf["memories"]:
        c = x["content"]
        tag = "<-- CORRECT (dislike)" if ("不喜欢" in c or "不爱" in c or "太甜" in c) else ""
        print(f"  [{x['id'][:12]}] {c} {tag}")

    # Cleanup
    for m in mf["memories"]:
        await memory.delete(m["id"])

    ok = (
        mf["total"] == 1
        and ("不喜欢" in mf["memories"][0]["content"] or "太甜" in mf["memories"][0]["content"])
    )
    return ok


if __name__ == "__main__":
    try:
        ok = asyncio.run(main())
        print("\nRESULT:", "PASS" if ok else "FAIL")
        sys.exit(0 if ok else 1)
    except Exception as e:
        import traceback

        traceback.print_exc()
        sys.exit(1)
