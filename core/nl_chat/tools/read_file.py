from langchain_core.tools import tool


@tool
async def read_file(file_path: str, max_lines: int = 100) -> str:
    """安全地读取文件内容。

    注意事项：
    - 只允许读取项目目录内的文件
    - 默认最多读取前100行内容以避免输出过长
    - 不支持读取二进制文件

    Args:
        file_path: 文件路径，可以是相对路径或绝对路径
        max_lines: 最多读取的行数，默认为100

    Returns:
        文件内容的文本
    """
    import os
    from pathlib import Path

    try:
        # 获取项目根目录，限制只能读取项目内的文件
        project_root = Path(__file__).parent.parent.parent
        project_root = project_root.resolve()

        # 解析文件路径
        file_path_obj = Path(file_path)
        if not file_path_obj.is_absolute():
            # 相对路径，相对于项目根目录
            file_path_obj = project_root / file_path_obj
        else:
            # 绝对路径，确保在项目根目录内
            try:
                file_path_obj = file_path_obj.resolve()
                # 检查是否在项目根目录内
                if not file_path_obj.is_relative_to(project_root):
                    return (
                        f"错误：只允许读取项目目录内的文件。项目根目录：{project_root}"
                    )
            except ValueError:
                return f"错误：无效的文件路径：{file_path}"

        # 检查文件是否存在
        if not file_path_obj.exists():
            return f"错误：文件不存在：{file_path_obj}"

        if not file_path_obj.is_file():
            return f"错误：路径不是文件：{file_path_obj}"

        # 检测是否为二进制文件
        try:
            with open(file_path_obj, "rb") as f:
                sample = f.read(1024)
            # 检查是否包含空字节（简单的二进制文件检测）
            if b"\x00" in sample:
                return f"错误：无法读取二进制文件：{file_path_obj}"
        except Exception as e:
            return f"错误：文件检测失败：{str(e)}"

        # 读取文件内容
        with open(file_path_obj, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # 限制读取行数
        if len(lines) > max_lines:
            content = "".join(lines[:max_lines])
            content += (
                f"\n\n... 已省略 {len(lines) - max_lines} 行内容（共 {len(lines)} 行）"
            )
        else:
            content = "".join(lines)

        return f"文件内容（{file_path_obj}）：\n{content}"

    except UnicodeDecodeError:
        return f"错误：文件编码不是UTF-8，无法读取：{file_path}"
    except Exception as e:
        return f"错误：读取文件失败：{str(e)}"
