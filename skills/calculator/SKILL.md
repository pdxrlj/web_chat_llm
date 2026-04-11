---
name: calculator
description: >
  数学计算器，支持基础运算、数学函数和常量。
  Use this skill whenever the user asks for 计算、算术、数学运算、calculator、
  math calculation, or wants to evaluate expressions like "2+3", "sqrt(16)".
license: MIT
---

# 数学计算器

当用户需要进行数学计算时，使用本技能。

## 如何使用

使用 `shell_execute` 工具执行以下命令来计算数学表达式：

```
uv run skills/calculator/calculator_script.py "表达式"
```

### 步骤

1. 从用户问题中提取数学表达式
2. 使用 `shell_execute` 工具执行：`uv run skills/calculator/calculator_script.py "表达式"`
3. 将计算结果以自然的方式告诉用户

### 示例

用户问 "2+3等于几"：
- 调用 `shell_execute`，命令为：`uv run skills/calculator/calculator_script.py "2 + 3"`
- 返回结果：2 + 3 = 5
- 回复用户：2+3等于5

用户问 "根号16"：
- 调用 `shell_execute`，命令为：`uv run skills/calculator/calculator_script.py "sqrt(16)"`
- 返回结果：sqrt(16) = 4
- 回复用户：√16 = 4

## 支持的运算

- 基础运算：+, -, *, /, //, %, **
- 数学函数：sqrt, sin, cos, tan, log, exp, abs, round, pow, log2, log10, factorial, gcd
- 三角函数：sin, cos, tan, asin, acos, atan, atan2, sinh, cosh, tanh
- 其他函数：ceil, floor, degrees, radians, min, max, sum
- 数学常量：pi, e, inf

## 表达式示例

| 用户说法 | shell_execute 命令中的表达式 |
|---------|---------------------------|
| 2+3 | `"2 + 3"` |
| 根号16 | `"sqrt(16)"` |
| sin(π/2) | `"sin(pi/2)"` |
| log100 | `"log(100, 10)" |
| 2的10次方 | `"2 ** 10"` |
| 15除以4的整数部分 | `"15 // 4"` |

## 注意事项

- 表达式必须是有效的 Python 数学表达式
- 只支持数学运算，不支持其他 Python 代码（安全限制）
- 如果计算出错，检查表达式语法是否正确
- 注意用引号包裹表达式，避免 shell 特殊字符问题
