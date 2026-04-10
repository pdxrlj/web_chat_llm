"""测试中文embedding相似度"""

import asyncio
import numpy as np
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


async def test_similarity():
    from core.memory.nl_memory import client
    
    memory = client()
    
    print(f"\n当前模型: {memory.embedding_model}")
    print("=" * 80)
    
    # 测试用例
    test_pairs = [
        ("喜欢吃葡萄", "不喜欢吃葡萄"),
        ("喜欢葡萄", "不喜欢葡萄"),
        ("名字叫派大星", "叫派大星"),
        ("喜欢苹果", "不喜欢苹果"),
        ("西红柿", "番茄"),
        ("我喜欢你", "我不喜欢你"),
        ("喜欢吃葡萄", "喜欢吃葡萄"),  # 完全相同
    ]
    
    for text1, text2 in test_pairs:
        emb1 = await memory._get_embedding(text1)
        emb2 = await memory._get_embedding(text2)
        
        v1 = np.array(emb1, dtype=np.float32)
        v2 = np.array(emb2, dtype=np.float32)
        
        dot_product = np.dot(v1, v2)
        norm_v1 = np.linalg.norm(v1)
        norm_v2 = np.linalg.norm(v2)
        similarity = dot_product / (norm_v1 * norm_v2)
        
        status = "[PASS]" if similarity >= 0.85 else "[FAIL]"
        
        print(f"{status} {similarity:.4f} | '{text1}' vs '{text2}'")


async def check_grape_memories():
    """检查葡萄相关记忆的实际相似度"""
    from core.memory.nl_memory import client
    
    memory = client()
    
    result = await memory.get_all(limit=50)
    all_memories = result['memories']
    
    grape_memories = [m for m in all_memories if '葡萄' in m['content']]
    
    print("\n" + "=" * 80)
    print("Grape memories similarity check")
    print(f"Threshold: {memory.similarity_threshold}")
    print("=" * 80)
    
    print(f"\nFound {len(grape_memories)} grape-related memories:")
    
    for i, mem1 in enumerate(grape_memories):
        emb1 = await memory._get_embedding(mem1['content'])
        
        for j, mem2 in enumerate(grape_memories):
            if i >= j:
                continue
            
            emb2 = await memory._get_embedding(mem2['content'])
            
            v1 = np.array(emb1, dtype=np.float32)
            v2 = np.array(emb2, dtype=np.float32)
            
            dot_product = np.dot(v1, v2)
            norm_v1 = np.linalg.norm(v1)
            norm_v2 = np.linalg.norm(v2)
            similarity = dot_product / (norm_v1 * norm_v2)
            
            status = "PASS" if similarity >= memory.similarity_threshold else "FAIL"
            print(f"  [{status}] {similarity:.4f} | '{mem1['content']}' <-> '{mem2['content']}'")


if __name__ == "__main__":
    import sys
    
    if "--check" in sys.argv:
        asyncio.run(check_grape_memories())
    else:
        asyncio.run(test_similarity())
