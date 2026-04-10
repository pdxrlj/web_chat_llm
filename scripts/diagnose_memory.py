"""记忆冲突诊断脚本 - 检测并展示冲突处理流程"""

import asyncio
import json
import logging
from datetime import datetime

# 配置日志（显示所有级别）
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def diagnose_conflict():
    """诊断记忆冲突处理"""
    
    print("=" * 80)
    print("记忆冲突诊断工具")
    print("=" * 80)
    
    # 导入
    from core.memory.nl_memory import client
    
    memory = client()
    
    # 显示配置信息
    print("\n[1] 当前配置")
    print("-" * 40)
    print(f"  相似度阈值: {memory.similarity_threshold}")
    print(f"  冲突检测: {'启用' if memory.enable_conflict_detection else '禁用'}")
    print(f"  LLM模型: {memory.openai_model}")
    
    # 获取当前所有记忆
    print("\n[2] 当前记忆列表")
    print("-" * 40)
    result = await memory.get_all(limit=100)
    all_memories = result.get('memories', [])
    print(f"  总数: {len(all_memories)}")
    
    # 找出葡萄相关的记忆
    grape_memories = [m for m in all_memories if '葡萄' in m['content']]
    if grape_memories:
        print(f"\n  ⚠️ 发现 {len(grape_memories)} 条关于'葡萄'的记忆:")
        for i, mem in enumerate(grape_memories):
            print(f"    [{i+1}] ID: {mem['id'][:16]}... | 内容: '{mem['content']}' | 类型: {mem['memory_type']}")
    
    # 测试添加新记忆
    print("\n[3] 测试冲突检测")
    print("-" * 40)
    
    test_content = "我不喜欢吃葡萄了"
    print(f"  准备添加新记忆: '{test_content}'")
    
    # 手动模拟 add 过程
    messages = [{"role": "user", "content": test_content}]
    
    try:
        # 调用 add 并观察日志
        print("\n  开始调用 add()...")
        add_result = await memory.add(
            messages=messages,
            user_id="pdx",
            infer=True,
            auto_detect_conflict=True
        )
        
        print(f"\n[4] 添加结果")
        print("-" * 40)
        print(f"  提取的记忆数: {add_result.get('memories_extracted')}")
        print(f"  实际存储数: {add_result.get('memories_added')}")
        print(f"  检测到冲突: {add_result.get('conflicts_detected')}")
        
        # 显示时间统计
        timing = add_result.get('timing', {})
        if timing:
            print(f"\n  时间统计:")
            print(f"    提取耗时: {timing.get('extract', 0):.3f}s")
            print(f"    Embedding: {timing.get('embed', 0):.3f}s")
            print(f"    冲突检测: {timing.get('conflict', 0):.3f}s")
            print(f"    总计: {timing.get('total', 0):.3f}s")
        
    except Exception as e:
        print(f"\n  ❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 验证最终结果
    print("\n[5] 验证结果")
    print("-" * 40)
    final_result = await memory.get_all(limit=100)
    final_memories = final_result.get('memories', [])
    
    final_grape = [m for m in final_memories if '葡萄' in m['content']]
    print(f"  最终葡萄相关记忆数: {len(final_grape)}")
    
    if final_grape:
        for i, mem in enumerate(final_grape):
            status = "❌ 冲突!" if len(final_grape) > 1 else "✓"
            print(f"    [{i+1}] {status} ID: {mem['id'][:16]}... | 内容: '{mem['content']}'")
    else:
        print("    (无)")
    
    # 总结
    print("\n" + "=" * 80)
    if len(final_grape) <= 1:
        print("✓ 冲突处理正确！只保留最新偏好")
    else:
        print("✗ 存在问题！仍然有多个冲突记忆")
        print("\n可能原因:")
        print("  1. 相似度阈值过低（已调整为0.85）")
        print("  2. LLM判断不准确")
        print("  3. delete_ids未正确返回")
        print("\n建议:")
        print("  1. 重启服务使配置生效")
        print("  2. 运行清理脚本: uv run python scripts/clean_memory.py")
    print("=" * 80)


async def test_direct_conflict():
    """直接测试冲突场景"""
    from core.memory.nl_memory import client
    
    print("\n" + "=" * 80)
    print("直接冲突测试")
    print("=" * 80)
    
    memory = client()
    
    # 步骤1: 先添加"喜欢葡萄"
    print("\n步骤1: 添加 '喜欢葡萄'")
    r1 = await memory.add([{"role":"user","content":"我喜欢吃葡萄"}], user_id="test_user")
    print(f"  结果: 存储 {r1['memories_added']} 条")
    
    # 验证
    check1 = await memory.get_all(user_id="test_user")
    grape1 = [m for m in check1['memories'] if '葡萄' in m['content']]
    print(f"  当前葡萄记忆: {[m['content'] for m in grape1]}")
    
    # 步骤2: 再添加"不喜欢葡萄"
    print("\n步骤2: 添加 '不喜欢吃葡萄'")
    r2 = await memory.add([{"role":"user","content":"我不喜欢吃葡萄"}], user_id="test_user")
    print(f"  结果: 存储 {r2['memories_added']} 条, 冲突: {r2['conflicts_detected']}")
    
    # 验证最终结果
    check2 = await memory.get_all(user_id="test_user")
    grape2 = [m for m in check2['memories'] if '葡萄' in m['content']]
    print(f"\n最终葡萄记忆 ({len(grape2)}条):")
    for m in grape2:
        print(f"  - {m['content']}")
    
    # 判断
    if len(grape2) == 1 and '不' in grape2[0]['content']:
        print("\n✓ 测试通过! 正确替换为'不喜欢'")
    elif len(grape2) == 1 and '不' not in grape2[0]['content']:
        print("\n⚠ 只保留了旧记忆, 新记忆被跳过")
    else:
        print(f"\n❌ 测试失败! 应该只有1条, 实际{len(grape2)}条")
        print("\n调试信息:")
        print(f"  冲突检测结果: {r2['conflicts_detected']}")
        print(f"  相似度阈值: {memory.similarity_threshold}")


if __name__ == "__main__":
    import sys
    
    if "--test" in sys.argv:
        asyncio.run(test_direct_conflict())
    else:
        asyncio.run(diagnose_conflict())
