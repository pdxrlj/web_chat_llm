"""记忆数据清理脚本 - 清理冲突、重复、过时的记忆"""

import asyncio
import logging
from datetime import datetime

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def clean_memory_data():
    """
    清理记忆数据的完整流程：
    
    1. 获取所有记忆
    2. 按主题分组（基于关键词）
    3. 对每组进行冲突检测和合并
    4. 删除冗余记忆
    """
    from core.memory.nl_memory import client
    
    memory = client()
    
    print("=" * 80)
    print("开始记忆数据清理...")
    print("=" * 80)
    
    # 1. 获取所有记忆
    print("\n[步骤1] 获取所有记忆...")
    result = await memory.get_all(limit=500)
    all_memories = result.get('memories', [])
    
    print(f"  总记忆数: {len(all_memories)}")
    
    if not all_memories:
        print("  无记忆数据，无需清理")
        return
    
    # 显示当前所有记忆
    print("\n[当前记忆列表]")
    for i, mem in enumerate(all_memories):
        print(f"  [{i+1}] {mem['content'][:40]:<42} | {mem['memory_type']:<10} | {mem['id'][:12]}")
    
    # 2. 检测并解决冲突
    print("\n[步骤2] 开始智能整理...")
    print("-" * 80)
    
    organize_result = await memory.organize(user_id=None)  # 整理全部用户
    
    # 3. 显示结果
    print("\n[整理结果]")
    print(f"  扫描总数: {organize_result['total_scanned']}")
    print(f"  解决冲突: {organize_result['conflicts_resolved']}")
    print(f"  删除数量: {organize_result['memories_deleted']}")
    
    # 4. 验证结果
    print("\n[步骤3] 验证清理结果...")
    result_after = await memory.get_all(limit=500)
    memories_after = result_after.get('memories', [])
    
    print(f"\n  清理后总记忆数: {len(memories_after)}")
    print(f"  减少数量: {len(all_memories) - len(memories_after)}")
    
    if memories_after:
        print("\n[清理后记忆列表]")
        for i, mem in enumerate(memories_after):
            print(f"  [{i+1}] {mem['content'][:42]:<44} | {mem['memory_type']:<10}")
    
    print("\n" + "=" * 80)
    print("记忆数据清理完成!")
    print("=" * 80)
    
    return {
        'before_count': len(all_memories),
        'after_count': len(memories_after),
        'deleted': organize_result['memories_deleted'],
        'resolved': organize_result['conflicts_resolved']
    }


async def analyze_memory_conflicts():
    """分析当前的冲突情况"""
    from core.memory.nl_memory import client
    
    memory = client()
    
    print("\n[冲突分析报告]")
    print("=" * 80)
    
    result = await memory.get_all(limit=500)
    all_memories = result.get('memories', [])
    
    # 按内容类型分组
    preference_memories = [m for m in all_memories if m['memory_type'] == 'preference']
    fact_memories = [m for m in all_memories if m['memory_type'] == 'fact']
    
    print(f"\n偏好类记忆 (preference): {len(preference_memories)}")
    for i, mem in enumerate(preference_memories[:20]):
        print(f"  [{i+1}] {mem['content']} (ID: {mem['id'][:12]}...)")
    
    if len(preference_memories) > 20:
        print(f"  ... 还有 {len(preference_memories) - 20} 条")
    
    print(f"\n事实类记忆 (fact): {len(fact_memories)}")
    for i, mem in enumerate(fact_memories[:10]):
        print(f"  [{i+1}] {mem['content']} (ID: {mem['id'][:12]}...)")
    
    if len(fact_memories) > 10:
        print(f"  ... 还有 {len(fact_memories) - 10} 条")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--analyze":
        # 分析模式：查看当前状态
        asyncio.run(analyze_memory_conflicts())
    else:
        # 默认模式：执行清理
        asyncio.run(clean_memory_data())
