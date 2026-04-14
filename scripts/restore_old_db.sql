-- ============================================================
-- 修复脚本：恢复 chat_web 数据库的 users.session_id 列
-- 原因：新项目迁移时删除了该列，导致老项目报错
-- 执行方式：psql -h 112.132.224.74 -p 35432 -U postgres -d chat_web -f restore_old_db.sql
-- ============================================================

-- 1. 恢复 users 表的 session_id 列
ALTER TABLE users ADD COLUMN IF NOT EXISTS session_id VARCHAR(100);

-- 2. 从 user_sessions 表回填 session_id（取每个用户的第一条会话）
UPDATE users SET session_id = us.session_id
FROM (
    SELECT DISTINCT ON (user_id) user_id, session_id
    FROM user_sessions
    ORDER BY user_id, created_at ASC
) AS us
WHERE users.id = us.user_id AND users.session_id IS NULL;

-- 3. 验证
SELECT id, username, session_id FROM users;
