"""计算器 Skill - 安全的数学计算工具

功能特性：
- 支持基础运算（+, -, *, /, //, %, **）
- 支持数学函数（sqrt, sin, cos, tan, log, exp 等）
- 支持数学常量（pi, e）
- 安全的 AST 解析（防止代码注入）

使用示例：
    ```python
    from skills.calculator import calculate

    # 计算表达式
    result = calculate("2 + 3 * 4")  # 输出: 14
    result = calculate("sqrt(16)")   # 输出: 4
    result = calculate("sin(pi/2)")  # 输出: 1.0
    ```
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 直接导入计算器模块
from .calculator_script import calculate as _calculate_script


async def calculate(expression: str) -> str:
    """计算数学表达式

    支持的运算：
    - 基础运算：+, -, *, /, //, %, **
    - 数学函数：sqrt, sin, cos, tan, log, exp, abs, round 等
    - 数学常量：pi, e

    Args:
        expression: 数学表达式（如 "2 + 3 * 4", "sqrt(16)", "sin(pi/2)"）

    Returns:
        计算结果字符串

    Example:
        ```python
        result = await calculate("2 + 3 * 4")
        # 输出: "2 + 3 * 4 = 14"

        result = await calculate("sqrt(16)")
        # 输出: "sqrt(16) = 4"

        result = await calculate("sin(pi/2)")
        # 输出: "sin(pi/2) = 1.0"
        ```
    """
    try:
        logger.info(f"开始计算: {expression}")
        
        # 直接调用内部计算函数（参考 web_scraper 的执行方式）
        result = _calculate_script(expression)
        
        logger.info(f"计算成功: {result}")
        return result

    except Exception as e:
        logger.error(f"计算异常: {str(e)} 表达式: {expression}", exc_info=True)
        return f"错误：{str(e)}"


def calculate_sync(expression: str) -> str:
    """计算数学表达式（同步版本）

    Args:
        expression: 数学表达式

    Returns:
        计算结果字符串
    """
    try:
        logger.info(f"开始计算（同步）: {expression}")
        
        # 直接调用内部计算函数
        result = _calculate_script(expression)
        
        logger.info(f"计算成功: {result}")
        return result

    except Exception as e:
        logger.error(f"计算异常: {str(e)} 表达式: {expression}", exc_info=True)
        return f"错误：{str(e)}"


# 导出公共 API
__all__ = [
    "calculate",
    "calculate_sync",
]
