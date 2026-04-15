"""美化打印工具模块 - 基于 rich 库的表格/面板美化输出"""

from io import StringIO

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from core.config import config


def _is_enabled() -> bool:
    """检查美化打印是否开启"""
    return config.app.pretty_print


def _render(rich_obj: object) -> str:
    """将 rich 对象渲染为字符串"""
    buf = StringIO()
    console = Console(file=buf, force_terminal=True)
    console.print(rich_obj)
    return buf.getvalue()


def table(
    title: str,
    data: dict[str, str | int | float],
    *,
    border_style: str = "bright_blue",
    title_style: str = "bold cyan",
    header_style: str = "bold magenta",
    value_style: str = "bold green",
    show_lines: bool = True,
) -> str | None:
    """生成美化表格字符串

    Args:
        title: 表格标题
        data: 键值对数据，key 为 Field，value 为 Value
        border_style: 边框颜色
        title_style: 标题颜色
        header_style: 表头颜色
        value_style: 值颜色
        show_lines: 是否显示行分割线

    Returns:
        美化后的表格字符串，如果未开启则返回 None
    """
    if not _is_enabled():
        return None

    t = Table(
        title=title,
        title_style=title_style,
        border_style=border_style,
        show_lines=show_lines,
    )
    t.add_column("Field", style=header_style, justify="right")
    t.add_column("Value", style=value_style)

    for key, value in data.items():
        t.add_row(str(key), str(value))

    return _render(t)


def panel(
    content: str,
    *,
    title: str = "",
    border_style: str = "bright_blue",
    title_style: str = "bold cyan",
    content_style: str = "white",
) -> str | None:
    """生成美化面板字符串

    Args:
        content: 面板内容
        title: 面板标题
        border_style: 边框颜色
        title_style: 标题颜色
        content_style: 内容颜色

    Returns:
        美化后的面板字符串，如果未开启则返回 None
    """
    if not _is_enabled():
        return None

    text = Text(content, style=content_style)
    styled_title = Text(title, style=title_style) if title else ""
    p = Panel(text, title=styled_title, border_style=border_style)
    return _render(p)


def log_table(
    logger: object, title: str, data: dict[str, str | int | float], **kwargs: object
) -> None:
    """便捷方法：生成美化表格并写入 logger

    Args:
        logger: logger 实例（需要有 info 方法）
        title: 表格标题
        data: 键值对数据
        **kwargs: 传递给 table() 的额外参数
    """
    result = table(title, data, **kwargs)  # type: ignore[arg-type]
    if result is not None:
        logger.info(result)  # type: ignore[union-attr]
    else:
        # 未开启美化打印时，使用普通格式
        parts = [f"{k}: {v}" for k, v in data.items()]
        logger.info(f"{title} - " + ", ".join(parts))  # type: ignore[union-attr]
