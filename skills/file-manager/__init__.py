"""文件管理 Skill - 文件读写、目录管理与 Shell 执行

功能特性：
- 文件读取（支持文本文件和 Markdown 解析）
- 文件写入和追加
- 目录列表
- 文件删除
- Shell 命令执行
- Markdown 文档解析（提取标题、链接、代码块等结构化信息）

使用示例：
    ```python
    from skills.file_manager import file_read, file_write, parse_markdown

    # 读取文件
    content = await file_read("/path/to/file.txt")

    # 写入文件
    result = await file_write("/path/to/file.txt", "Hello World")

    # 解析 Markdown
    result = await parse_markdown("/path/to/doc.md")
    ```
"""

import os
import subprocess
import logging
from pathlib import Path
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)


# ======================== 文件管理工具 ========================

async def file_read(file_path: str) -> str:
    """读取文件内容。

    支持文本文件和 Markdown 文件的读取，自动检测编码。

    Args:
        file_path: 文件路径（绝对路径或相对路径）

    Returns:
        文件内容字符串
    """
    try:
        path = Path(file_path).expanduser().resolve()
        if not path.exists():
            return f"错误：文件不存在 - {path}"
        if not path.is_file():
            return f"错误：路径不是文件 - {path}"
        content = path.read_text(encoding="utf-8")
        # 截断过大文件
        if len(content) > 50000:
            content = content[:50000] + f"\n... (文件过大，已截断，总长度: {len(content)} 字符)"
        return content
    except Exception as e:
        return f"读取文件失败: {e}"


async def file_write(file_path: str, content: str) -> str:
    """写入内容到文件。如果文件不存在会自动创建，存在则覆盖。

    Args:
        file_path: 文件路径（绝对路径或相对路径）
        content: 要写入的内容

    Returns:
        操作结果
    """
    try:
        path = Path(file_path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"成功写入 {len(content)} 字符到 {path}"
    except Exception as e:
        return f"写入文件失败: {e}"


async def file_append(file_path: str, content: str) -> str:
    """追加内容到文件末尾。如果文件不存在会自动创建。

    Args:
        file_path: 文件路径
        content: 要追加的内容

    Returns:
        操作结果
    """
    try:
        path = Path(file_path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(content)
        return f"成功追加 {len(content)} 字符到 {path}"
    except Exception as e:
        return f"追加文件失败: {e}"


async def file_list(directory: str = ".", pattern: str = "*") -> str:
    """列出目录中的文件和子目录。

    Args:
        directory: 目录路径，默认为当前目录
        pattern: 文件匹配模式，如 "*.py"、"*.txt"，默认为 "*"（全部）

    Returns:
        文件列表
    """
    try:
        path = Path(directory).expanduser().resolve()
        if not path.exists():
            return f"错误：目录不存在 - {path}"
        if not path.is_dir():
            return f"错误：路径不是目录 - {path}"

        entries = sorted(path.glob(pattern))
        if not entries:
            return f"目录 {path} 中没有匹配 '{pattern}' 的文件"

        lines = [f"目录: {path} (匹配: {pattern})\n"]
        for entry in entries[:200]:
            size = ""
            if entry.is_file():
                try:
                    size = f" ({entry.stat().st_size} bytes)"
                except OSError:
                    pass
            type_tag = "📁" if entry.is_dir() else "📄"
            lines.append(f"  {type_tag} {entry.name}{size}")

        if len(entries) > 200:
            lines.append(f"  ... 共 {len(entries)} 项，只显示前 200 项")

        return "\n".join(lines)
    except Exception as e:
        return f"列出目录失败: {e}"


async def file_delete(file_path: str) -> str:
    """删除文件。

    Args:
        file_path: 要删除的文件路径

    Returns:
        操作结果
    """
    try:
        path = Path(file_path).expanduser().resolve()
        if not path.exists():
            return f"错误：文件不存在 - {path}"
        if not path.is_file():
            return f"错误：路径不是文件 - {path}"
        path.unlink()
        return f"成功删除文件: {path}"
    except Exception as e:
        return f"删除文件失败: {e}"


# ======================== Shell 工具 ========================

async def shell_execute(command: str, timeout: int = 30) -> str:
    """执行Shell命令并返回输出。

    Args:
        command: 要执行的Shell命令
        timeout: 超时时间（秒），默认30秒

    Returns:
        命令的标准输出和标准错误
    """
    try:
        logger.info(f"Shell执行: {command}")
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )

        output_parts = []
        if result.stdout:
            output_parts.append(f"stdout:\n{result.stdout}")
        if result.stderr:
            output_parts.append(f"stderr:\n{result.stderr}")

        output = "\n".join(output_parts) if output_parts else "(无输出)"
        exit_info = f"\n退出码: {result.returncode}"

        # 截断过长输出
        if len(output) > 10000:
            output = output[:10000] + f"\n... (输出过长，已截断，总长度: {len(output)} 字符)"

        return output + exit_info
    except subprocess.TimeoutExpired:
        return f"命令执行超时（{timeout}秒）: {command}"
    except Exception as e:
        return f"执行命令失败: {e}"


# ======================== Markdown 解析工具 ========================

async def parse_markdown(file_path: str, extract_metadata: bool = True) -> str:
    """解析 Markdown 文档，提取结构化信息。

    支持提取：
    - YAML frontmatter（元数据）
    - 标题层级结构
    - 链接列表
    - 代码块
    - 表格
    - 图片引用

    Args:
        file_path: Markdown 文件路径
        extract_metadata: 是否提取 frontmatter 元数据

    Returns:
        解析结果（格式化文本）
    """
    try:
        path = Path(file_path).expanduser().resolve()
        if not path.exists():
            return f"错误：文件不存在 - {path}"
        if not path.is_file():
            return f"错误：路径不是文件 - {path}"

        content = path.read_text(encoding="utf-8")

        if len(content) > 100000:
            return f"错误：文件过大（{len(content)} 字符），最大支持 100000 字符"

        result_parts = []
        result_parts.append(f"📄 Markdown 解析结果: {path.name}\n")

        # 1. 解析 YAML frontmatter
        frontmatter = {}
        body = content
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                try:
                    import yaml
                    frontmatter = yaml.safe_load(parts[1]) or {}
                    body = parts[2].strip()
                    result_parts.append("## Frontmatter 元数据\n")
                    for key, value in frontmatter.items():
                        result_parts.append(f"- **{key}**: {value}")
                    result_parts.append("")
                except Exception:
                    body = content

        # 2. 提取标题结构
        import re
        headings = re.findall(r'^(#{1,6})\s+(.+)$', body, re.MULTILINE)
        if headings:
            result_parts.append("## 标题结构\n")
            for level_marks, title in headings:
                level = len(level_marks)
                indent = "  " * (level - 1)
                result_parts.append(f"{indent}- H{level}: {title}")
            result_parts.append("")

        # 3. 提取链接
        links = re.findall(r'\[([^\]]*)\]\(([^)]+)\)', body)
        if links:
            result_parts.append("## 链接\n")
            for text, url in links:
                result_parts.append(f"- [{text}]({url})")
            result_parts.append("")

        # 4. 提取图片
        images = re.findall(r'!\[([^\]]*)\]\(([^)]+)\)', body)
        if images:
            result_parts.append("## 图片\n")
            for alt, src in images:
                result_parts.append(f"- ![{alt}]({src})")
            result_parts.append("")

        # 5. 提取代码块
        code_blocks = re.findall(r'```(\w*)\n(.*?)```', body, re.DOTALL)
        if code_blocks:
            result_parts.append("## 代码块\n")
            for lang, code in code_blocks:
                lang_label = f" ({lang})" if lang else ""
                preview = code.strip()[:200]
                if len(code.strip()) > 200:
                    preview += "..."
                result_parts.append(f"- 代码块{lang_label}: {len(code.strip())} 字符")
                result_parts.append(f"  预览: {preview}")
            result_parts.append("")

        # 6. 提取表格
        tables = re.findall(r'(\|.+\|\n\|[-| :]+\|\n(?:\|.+\|\n)*)', body)
        if tables:
            result_parts.append("## 表格\n")
            for i, table in enumerate(tables, 1):
                rows = table.strip().split("\n")
                result_parts.append(f"- 表格 {i}: {len(rows) - 1} 行数据")
            result_parts.append("")

        # 7. 统计信息
        result_parts.append("## 统计信息\n")
        result_parts.append(f"- 总字符数: {len(content)}")
        result_parts.append(f"- 标题数: {len(headings)}")
        result_parts.append(f"- 链接数: {len(links)}")
        result_parts.append(f"- 图片数: {len(images)}")
        result_parts.append(f"- 代码块数: {len(code_blocks)}")
        result_parts.append(f"- 表格数: {len(tables)}")
        if frontmatter:
            result_parts.append(f"- Frontmatter 字段数: {len(frontmatter)}")

        return "\n".join(result_parts)

    except Exception as e:
        return f"解析 Markdown 失败: {e}"


# 同步版本（供内部使用）
def file_read_sync(file_path: str) -> str:
    try:
        path = Path(file_path).expanduser().resolve()
        if not path.exists():
            return f"错误：文件不存在 - {path}"
        if not path.is_file():
            return f"错误：路径不是文件 - {path}"
        content = path.read_text(encoding="utf-8")
        if len(content) > 50000:
            content = content[:50000] + f"\n... (文件过大，已截断，总长度: {len(content)} 字符)"
        return content
    except Exception as e:
        return f"读取文件失败: {e}"


# 导出公共 API
__all__ = [
    "file_read",
    "file_write",
    "file_append",
    "file_list",
    "file_delete",
    "shell_execute",
    "parse_markdown",
]
