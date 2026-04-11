#!/usr/bin/env python3
"""
独立的计算器脚本

使用方式：
    uv run calculator_script.py "2 + 3"
    uv run calculator_script.py "10 / 4"
    uv run calculator_script.py "sqrt(16)"
"""

import ast
import math
import operator
import sys
from typing import Any


# 支持的运算符
OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.LShift: operator.lshift,
    ast.RShift: operator.rshift,
    ast.BitOr: operator.or_,
    ast.BitXor: operator.xor,
    ast.BitAnd: operator.and_,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# 支持的数学函数
MATH_FUNCTIONS = {
    # 基础函数
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    # 数学函数
    "sqrt": math.sqrt,
    "pow": math.pow,
    "exp": math.exp,
    "log": math.log,
    "log10": math.log10,
    "log2": math.log2,
    # 三角函数
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "atan2": math.atan2,
    "sinh": math.sinh,
    "cosh": math.cosh,
    "tanh": math.tanh,
    # 其他函数
    "ceil": math.ceil,
    "floor": math.floor,
    "factorial": math.factorial,
    "gcd": math.gcd,
    "degrees": math.degrees,
    "radians": math.radians,
}

# 数学常量
MATH_CONSTANTS = {
    "pi": math.pi,
    "e": math.e,
    "inf": math.inf,
    "nan": math.nan,
}


class SafeCalculator(ast.NodeVisitor):
    """安全的计算器（AST 解析器）"""

    def __init__(self):
        self.result = None

    def visit(self, node: ast.AST) -> Any:
        """访问 AST 节点"""
        method = "visit_" + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)
        return visitor(node)

    def visit_Expression(self, node: ast.Expression) -> Any:
        """表达式"""
        return self.visit(node.body)

    def visit_BinOp(self, node: ast.BinOp) -> Any:
        """二元运算"""
        left = self.visit(node.left)
        right = self.visit(node.right)
        op_type = type(node.op)

        if op_type not in OPERATORS:
            raise ValueError(f"不支持的运算符: {op_type.__name__}")

        return OPERATORS[op_type](left, right)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        """一元运算"""
        operand = self.visit(node.operand)
        op_type = type(node.op)

        if op_type not in OPERATORS:
            raise ValueError(f"不支持的运算符: {op_type.__name__}")

        return OPERATORS[op_type](operand)

    def visit_Call(self, node: ast.Call) -> Any:
        """函数调用"""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id

            if func_name not in MATH_FUNCTIONS:
                raise ValueError(f"不支持的函数: {func_name}")

            func = MATH_FUNCTIONS[func_name]
            args = [self.visit(arg) for arg in node.args]

            return func(*args)
        else:
            raise ValueError("只支持直接函数调用")

    def visit_Name(self, node: ast.Name) -> Any:
        """变量名（常量）"""
        name = node.id

        if name in MATH_CONSTANTS:
            return MATH_CONSTANTS[name]
        else:
            raise ValueError(f"未知变量: {name}")

    def visit_Constant(self, node: ast.Constant) -> Any:
        """常量"""
        return node.value

    def generic_visit(self, node: ast.AST) -> Any:
        """默认访问（不允许其他节点）"""
        raise ValueError(f"不支持的语法: {node.__class__.__name__}")


def calculate(expression: str) -> str:
    """计算表达式

    Args:
        expression: 数学表达式

    Returns:
        计算结果
    """
    try:
        # 清理表达式
        expression = expression.strip()

        if not expression:
            return "错误：表达式为空"

        # 解析 AST
        tree = ast.parse(expression, mode="eval")

        # 安全计算
        calculator = SafeCalculator()
        result = calculator.visit(tree)

        # 格式化结果
        if isinstance(result, float):
            # 处理浮点数精度问题
            if result.is_integer():
                result = int(result)
            else:
                result = round(result, 10)  # 保留 10 位小数

        return f"{expression} = {result}"

    except ValueError as e:
        return f"错误：{str(e)}"
    except SyntaxError as e:
        return f"语法错误：{str(e)}"
    except Exception as e:
        return f"计算错误：{str(e)}"


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("使用方式: uv run calculator_script.py <expression>")
        print("示例:")
        print("  uv run calculator_script.py '2 + 3'")
        print("  uv run calculator_script.py 'sqrt(16)'")
        print("  uv run calculator_script.py 'sin(pi/2)'")
        sys.exit(1)
    print(f"*************************使用计算器计算:{sys.argv}")
    expression = sys.argv[1]
    result = calculate(expression)
    print(result)


if __name__ == "__main__":
    main()
