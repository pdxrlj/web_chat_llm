"""系统工具集 - 文件管理与Shell执行（替代 langchain_community 的 FileManagementToolkit 和 ShellTool）"""

import os
import subprocess
import logging
from pathlib import Path
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# ======================== 文件管理工具 ========================

@tool
def file_read(file_path: str) -> str:
    """读取文件内容。

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


@tool
def file_write(file_path: str, content: str) -> str:
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


@tool
def file_append(file_path: str, content: str) -> str:
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


@tool
def file_list(directory: str = ".", pattern: str = "*") -> str:
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
        for entry in entries[:200]:  # 限制输出数量
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


@tool
def file_delete(file_path: str) -> str:
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

@tool
def shell_execute(command: str, timeout: int = 30) -> str:
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


# ======================== 工具集合 ========================

def get_file_management_tools():
    """获取文件管理工具列表（等价于 langchain_community 的 FileManagementToolkit）"""
    return [file_read, file_write, file_append, file_list, file_delete]


def get_shell_tools():
    """获取Shell工具列表（等价于 langchain_community 的 ShellTool）"""
    return [shell_execute]


def get_all_system_tools():
    """获取全部系统工具"""
    return get_file_management_tools() + get_shell_tools()
