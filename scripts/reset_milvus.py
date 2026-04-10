"""重置Milvus集合 - 切换中文embedding模型后必须执行"""

import asyncio
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


async def reset_milvus_collection():
    """删除旧的async_memory集合"""
    try:
        from pymilvus import connections, utility
        
        # 连接Milvus（必须指定 db_name！）
        print("Connecting to Milvus...")
        connections.connect(
            alias="default",
            uri="http://8.153.82.167:19530",
            token="root:aibuddy@2025",
            db_name="web_chat",  # 必须指定正确的数据库
        )
        
        collection_name = "async_memory"
        
        if utility.has_collection(collection_name):
            print(f"Dropping old collection '{collection_name}'...")
            utility.drop_collection(collection_name)
            print(f"[OK] Collection '{collection_name}' dropped successfully!")
            
            # 显示所有剩余集合
            collections = utility.list_collections()
            print(f"\nRemaining collections: {collections}")
        else:
            print(f"Collection '{collection_name}' does not exist, no need to drop")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            connections.disconnect("default")
        except:
            pass


if __name__ == "__main__":
    print("=" * 80)
    print("Reset Milvus Collection - Required after switching embedding model")
    print("=" * 80)
    
    asyncio.run(reset_milvus_collection())
    
    print("\n" + "=" * 80)
    print("Next steps:")
    print("1. Restart the service: uv run python main.py")
    print("2. Test with: uv run python scripts/test_similarity.py")
    print("=" * 80)
