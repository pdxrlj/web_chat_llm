# File Manager Skill

文件管理、Shell 执行与 Markdown 解析技能。

## 功能特性

### 文件管理
- **file_read** - 读取文件内容（自动 UTF-8 解码，50KB 截断）
- **file_write** - 写入文件（覆盖模式，自动创建目录）
- **file_append** - 追加内容到文件末尾
- **file_list** - 列出目录内容（支持 glob 模式匹配）
- **file_delete** - 删除文件

### Shell 执行
- **shell_execute** - 执行 Shell 命令（30 秒超时，10KB 输出截断）

### Markdown 解析
- **parse_markdown** - 解析 Markdown 文档结构
  - YAML frontmatter 元数据提取
  - 标题层级结构（H1-H6）
  - 链接和图片引用提取
  - 代码块提取（含语言标识和预览）
  - 表格检测
  - 统计信息

## 使用方式

### 通过 Agent 调用

```
用户: "帮我读一下 /path/to/file.txt"
Agent → invoke_skill_tool("file_manager", "file_read", '{"file_path": "/path/to/file.txt"}')

用户: "解析这个 Markdown 文件"
Agent → invoke_skill_tool("file_manager", "parse_markdown", '{"file_path": "/path/to/doc.md"}')

用户: "执行 ls -la"
Agent → invoke_skill_tool("file_manager", "shell_execute", '{"command": "ls -la"}')
```

### Python 直接调用

```python
from skills.file_manager import file_read, parse_markdown

# 读取文件
content = await file_read("/path/to/file.txt")

# 解析 Markdown
result = await parse_markdown("/path/to/doc.md")
```

## 安全特性

- 文件读取有 50KB 截断保护
- Shell 命令有 30 秒超时
- Shell 输出有 10KB 截断
- Markdown 解析有 100KB 文件大小限制
- 文件路径自动 expanduser 和 resolve

## 项目结构

```
skills/file_manager/
├── __init__.py       # 工具实现（所有异步函数）
├── skill.yaml        # 技能配置 + 工具定义
└── README.md         # 使用文档
```
