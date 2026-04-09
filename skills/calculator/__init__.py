"""计算器 Skill - 通过 uv run 执行数学计算

功能特性：
- 支持 uv run 方式执行计算器脚本
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

import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# 计算器脚本路径
_SCRIPT_PATH = Path(__file__).parent / "calculator_script.py"


async def calculate(expression: str) -> str:
    """计算数学表达式（通过 uv run 执行）
    
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
        
        # 检查脚本是否存在
        if not _SCRIPT_PATH.exists():
            return f"❌ 错误：计算器脚本不存在: {_SCRIPT_PATH}"
        
        # 使用 uv run 执行计算器脚本
        # uv run 会自动管理 Python 环境
        process = await asyncio.create_subprocess_exec(
            "uv",
            "run",
            str(_SCRIPT_PATH),
            expression,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        # 等待执行完成
        stdout, stderr = await process.communicate()
        
        # 解析输出
        if process.returncode == 0:
            result = stdout.decode("utf-8").strip()
            logger.info(f"计算成功: {result}")
            return f"成功: {result}"
        else:
            error = stderr.decode("utf-8").strip()
            logger.error(f"计算失败: {error}")
            return f"失败: {error}"
    
    except FileNotFoundError:
        logger.error("uv 命令未找到，请确保已安装 uv")
        return "错误：未找到 uv 命令，请安装 uv（pip install uv）"
    except Exception as e:
        logger.error(f"计算异常: {str(e)}")
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
        
        # 检查脚本是否存在
        if not _SCRIPT_PATH.exists():
            return f"❌ 错误：计算器脚本不存在: {_SCRIPT_PATH}"
        
        # 使用 uv run 执行计算器脚本
        result = subprocess.run(
            ["uv", "run", str(_SCRIPT_PATH), expression],
            capture_output=True,
            text=True,
            timeout=10,  # 10 秒超时
        )
        
        if result.returncode == 0:
            output = result.stdout.strip()
            logger.info(f"计算成功: {output}")
            return f"成功: {output}"
        else:
            error = result.stderr.strip()
            logger.error(f"计算失败: {error}")
            return f"失败: {error}"
    
    except FileNotFoundError:
        logger.error("uv 命令未找到")
        return "错误：未找到 uv 命令，请安装 uv（pip install uv）"
    except subprocess.TimeoutExpired:
        logger.error("计算超时")
        return "错误：计算超时（10秒）"
    except Exception as e:
        logger.error(f"计算异常: {str(e)}")
        return f"错误：{str(e)}"


# 导出公共 API
__all__ = [
    "calculate",
    "calculate_sync",
]
