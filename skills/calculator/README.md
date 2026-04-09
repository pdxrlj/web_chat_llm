# Calculator Skill

通过 `uv run` 执行的数学计算器技能。

## 🚀 功能特性

- ✅ **基础运算**：+, -, *, /, //, %, **
- ✅ **数学函数**：sqrt, sin, cos, tan, log, exp, abs, round 等
- ✅ **数学常量**：pi, e, inf, nan
- ✅ **安全执行**：AST 解析，防止代码注入
- ✅ **环境隔离**：通过 uv run 执行独立脚本

## 📦 使用方式

### 方式 1：直接执行脚本

```bash
# 基础运算
uv run skills/calculator/calculator_script.py "2 + 3 * 4"
# 输出: 2 + 3 * 4 = 14

# 数学函数
uv run skills/calculator/calculator_script.py "sqrt(16)"
# 输出: sqrt(16) = 4

# 三角函数
uv run skills/calculator/calculator_script.py "sin(pi/2)"
# 输出: sin(pi/2) = 1

# 对数函数
uv run skills/calculator/calculator_script.py "log(100, 10)"
# 输出: log(100, 10) = 2.0
```

### 方式 2：在 Python 中调用

```python
from skills.calculator import calculate

# 异步调用
result = await calculate("2 + 3 * 4")
print(result)  # ✅ 2 + 3 * 4 = 14

# 同步调用
from skills.calculator import calculate_sync
result = calculate_sync("sqrt(16)")
print(result)  # ✅ sqrt(16) = 4
```

### 方式 3：通过 Agent 调用

```python
# Agent 会自动调用 invoke_skill_tool
# 用户问题："帮我计算 2 + 3 * 4"
# Agent 决策：invoke_skill_tool("calculator", "calculate", expression="2 + 3 * 4")
```

## 🎯 支持的表达式

### 基础运算
```python
"2 + 3"          # 加法 → 5
"10 - 4"         # 减法 → 6
"3 * 4"          # 乘法 → 12
"15 / 4"         # 除法 → 3.75
"15 // 4"        # 整除 → 3
"17 % 5"         # 取模 → 2
"2 ** 10"        # 幂运算 → 1024
```

### 数学函数
```python
"abs(-5)"        # 绝对值 → 5
"round(3.7)"     # 四舍五入 → 4
"sqrt(16)"       # 平方根 → 4
"pow(2, 3)"      # 幂运算 → 8
"exp(1)"         # e 的幂 → 2.718...
"log(100, 10)"   # 对数 → 2.0
"log2(8)"        # 以 2 为底的对数 → 3.0
"log10(100)"     # 以 10 为底的对数 → 2.0
```

### 三角函数
```python
"sin(0)"         # 正弦 → 0
"cos(0)"         # 余弦 → 1
"tan(0)"         # 正切 → 0
"asin(1)"        # 反正弦 → 1.57...
"acos(0)"        # 反余弦 → 1.57...
"atan(1)"        # 反正切 → 0.78...
```

### 数学常量
```python
"pi"             # 圆周率 → 3.14159...
"e"              # 自然常数 → 2.71828...
"sin(pi/2)"      # → 1.0
"e ** 2"         # → 7.389...
```

### 复合表达式
```python
"2 + 3 * 4"                  # 运算符优先级 → 14
"(2 + 3) * 4"                # 括号 → 20
"sqrt(16) + pow(2, 3)"       # 函数组合 → 12
"sin(pi/4) + cos(pi/4)"      # 三角函数 → 1.414...
```

## 🛠️ 技术实现

### 架构设计

```
skills/calculator/
├── __init__.py              # Skill 接口（调用 uv run）
├── calculator_script.py     # 独立计算器脚本
└── skill.yaml               # Skill 配置
```

### 调用流程

```
用户输入 "计算 2 + 3 * 4"
    ↓
Agent 调用 invoke_skill_tool("calculator", "calculate", "2 + 3 * 4")
    ↓
__init__.py::calculate() 执行
    ↓
subprocess.run(["uv", "run", "calculator_script.py", "2 + 3 * 4"])
    ↓
calculator_script.py 解析表达式并计算
    ↓
返回结果 "2 + 3 * 4 = 14"
```

### 安全机制

1. **AST 解析**：使用 `ast.parse()` 解析表达式，只允许数学运算
2. **白名单函数**：只允许预定义的数学函数
3. **环境隔离**：通过 `uv run` 执行，不直接访问主进程
4. **超时限制**：同步调用默认 10 秒超时

## 📊 性能特性

| 特性 | 说明 |
|------|------|
| 执行方式 | uv run（环境隔离） |
| 超时时间 | 10 秒（同步） |
| 安全等级 | 高（AST 白名单） |
| 支持平台 | Windows/Linux/macOS |

## 🔧 开发指南

### 添加新的数学函数

编辑 `calculator_script.py`：

```python
# 在 MATH_FUNCTIONS 字典中添加
MATH_FUNCTIONS = {
    # ... 现有函数
    'hypot': math.hypot,  # 欧几里得距离
}
```

### 添加新的常量

```python
MATH_CONSTANTS = {
    # ... 现有常量
    'tau': math.tau,  # 2 * pi
}
```

## 🐛 故障排查

### 问题 1：uv 命令未找到

```bash
# 安装 uv
pip install uv
```

### 问题 2：表达式语法错误

确保表达式是有效的 Python 数学表达式：
- ❌ "2 plus 3"（错误：应该用 +）
- ✅ "2 + 3"

### 问题 3：不支持的函数

检查函数是否在白名单中：
- ❌ "print(123)"（错误：print 不是数学函数）
- ✅ "sqrt(16)"

## 📝 更新日志

### v1.0.0 (2026-04-09)
- 🎉 初始版本
- ✨ 支持基础运算、数学函数、常量
- ✨ 通过 uv run 执行
- ✨ AST 安全解析

## 📄 License

MIT License
