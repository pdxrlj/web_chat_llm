"""
修复脚本：
1. 恢复 chat_web 数据库的 users.session_id 列（修复老项目）
2. 从 user_sessions 回填 session_id 数据
3. 创建新数据库 chat_web_new（供新项目使用）
"""

import asyncio
import sys
import io
import asyncpg

# 修复 Windows 终端编码问题
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


DB_CONFIG = {
    "host": "112.132.224.74",
    "port": 35432,
    "user": "postgres",
    "password": "pg123",
}


async def main():
    # --- 第1步：恢复 chat_web 的 users.session_id 列 ---
    print(">>> 连接 chat_web 数据库...")
    conn = await asyncpg.connect(**DB_CONFIG, database="chat_web")

    print(">>> 恢复 users.session_id 列...")
    await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS session_id VARCHAR(100)")
    print("    [OK] session_id 列已恢复")

    # --- 第2步：从 user_sessions 回填 session_id ---
    print(">>> 从 user_sessions 回填 session_id...")
    result = await conn.execute("""
        UPDATE users SET session_id = us.session_id
        FROM (
            SELECT DISTINCT ON (user_id) user_id, session_id
            FROM user_sessions
            ORDER BY user_id, created_at ASC
        ) AS us
        WHERE users.id = us.user_id AND users.session_id IS NULL
    """)
    print(f"    [OK] 回填完成: {result}")

    # 验证
    rows = await conn.fetch("SELECT id, username, session_id FROM users")
    for row in rows:
        print(f"    用户: id={row['id']}, username={row['username']}, session_id={row['session_id']}")

    await conn.close()

    # --- 第3步：创建新数据库 chat_web_new ---
    print(">>> 创建新数据库 chat_web_new...")
    conn = await asyncpg.connect(**DB_CONFIG, database="postgres")
    # 设置为非事务自动提交模式
    await conn.execute("COMMIT")
    try:
        await conn.execute("CREATE DATABASE chat_web_new")
        print("    [OK] chat_web_new 数据库已创建")
    except asyncpg.DuplicateDatabaseError:
        print("    [WARN] chat_web_new 数据库已存在，跳过")
    await conn.close()

    print("\n>>> 全部完成！老项目已修复，新项目将使用 chat_web_new 数据库")


if __name__ == "__main__":
    asyncio.run(main())
