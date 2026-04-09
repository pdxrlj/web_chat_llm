# Skill 工具系统使用指南

## 🎯 概述

Skill 系统现在支持**可执行工具**！技能不仅包含专业指导，还能提供实际可执行的函数。

## 📁 目录结构

```
skills/
├── calculator.yaml         # 计算器技能（包含工具）
├── web_scraper.yaml        # Web 抓取技能（包含工具）
├── sql_expert.yaml         # SQL 专家（仅指导）
├── code_reviewer.yaml      # 代码审查（仅指导）
└── data_analyst.yaml       # 数据分析（仅指导）
```

## 🔧 技能 YAML 格式

### 包含工具的技能

```yaml
name: calculator
description: 计算器技能，提供数学计算和单位转换功能
version: 1.0.0
tags:
  - calculator
  - math

# 技能指导（可选）
content: |
  你可以使用计算器技能进行数学计算...

# 可执行工具定义
tools:
  - name: calculate
    description: 计算数学表达式
    parameters:
      expression:
        type: string
        description: 数学表达式，如 "2 + 3 * 4"
    code: |
      try:
          allowed_chars = set("0123456789+-*/(). ")
          if not all(c in allowed_chars for c in expression):
              return "错误：表达式包含不允许的字符"
          
          result = eval(expression)
          return f"计算结果: {result}"
      except Exception as e:
          return f"计算错误: {str(e)}"

  - name: unit_convert
    description: 单位转换
    parameters:
      value:
        type: number
        description: 数值
      from_unit:
        type: string
        description: 原始单位
      to_unit:
        type: string
        description: 目标单位
    code: |
      # 转换逻辑...
      return f"{value} {from_unit} = {result:.2f} {to_unit}"
```

### 仅指导的技能

```yaml
name: sql_expert
description: SQL 查询专家
version: 1.0.0

content: |
  你是 SQL 专家...
```

## 🚀 使用方式

### 1. 列出所有技能

```python
from core.nl_chat.chat import ChatAgent

agent = ChatAgent()

# Agent 自动获得 3 个工具：
# - list_skills: 列出所有技能
# - load_skill: 加载技能指导
# - invoke_skill_tool: 调用技能工具
```

### 2. 用户对话示例

```
用户: 帮我计算 2 + 3 * 4
Agent: [调用 list_skills] 发现 calculator 技能
       [调用 invoke_skill_tool("calculator", "calculate", expression="2 + 3 * 4")]
       返回: 计算结果: 14
```

```
用户: 将 10 公里转换为英里
Agent: [调用 invoke_skill_tool("calculator", "unit_convert", 
                                 value=10, from_unit="km", to_unit="mile")]
       返回: 10 km = 6.21 mile
```

```
用户: 抓取这个网页的内容 https://example.com
Agent: [调用 invoke_skill_tool("web_scraper", "fetch_webpage", 
                                 url="https://example.com")]
       返回: 成功抓取，内容长度: 1234 字符...
```

### 3. Agent 工具详解

#### `list_skills()`
列出所有可用技能，标记是否包含工具。

#### `load_skill(skill_name)`
加载技能的专业指导内容。

**参数**：
- `skill_name`: 技能名称

**返回**：技能指导文本

#### `invoke_skill_tool(skill_name, tool_name, **kwargs)`
调用技能中的可执行工具。

**参数**：
- `skill_name`: 技能名称
- `tool_name`: 工具名称
- `**kwargs`: 工具参数

**返回**：工具执行结果

## 📝 创建自定义技能

### 示例：创建一个简单的问候技能

```yaml
# skills/greeting.yaml
name: greeting
description: 问候技能，提供个性化问候
version: 1.0.0
tags:
  - greeting
  - utility

content: |
  你可以使用问候技能生成个性化问候语。

tools:
  - name: say_hello
    description: 生成问候语
    parameters:
      name:
        type: string
        description: 用户姓名
      time:
        type: string
        description: 时间（morning/afternoon/evening）
        default: "morning"
    code: |
      greetings = {
          "morning": "早上好",
          "afternoon": "下午好",
          "evening": "晚上好"
      }
      
      greeting = greetings.get(time, "你好")
      return f"{greeting}，{name}！"
```

### 测试

```python
# 测试技能工具
from core.nl_chat.skill_loader import SkillLoader

loader = SkillLoader("./skills")

# 加载工具
tools = loader.load_skill_tools("greeting")

# 执行工具
hello_tool = next(t for t in tools if t.name == "say_hello")
result = hello_tool.invoke({"name": "张三", "time": "morning"})

print(result)  # 输出: 早上好，张三！
```

## 🎓 工具参数类型

| 类型 | 说明 | 示例 |
|------|------|------|
| `string` | 字符串 | `"hello"` |
| `number` | 数字（浮点数） | `3.14` |
| `integer` | 整数 | `42` |
| `boolean` | 布尔值 | `true` |
| `array` | 数组 | `[1, 2, 3]` |

## ⚡ 性能优势

### 按需加载，避免工具积累

```python
# ❌ 传统方式：预加载所有工具
tools = [tool1, tool2, tool3, ...]  # 列表持续增长

# ✅ 本方案：按需调用
invoke_skill_tool("calculator", "calculate", ...)  # 只在需要时加载
```

### LRU 缓存自动管理

```python
loader = SkillLoader(cache_size=10)  # 缓存最近 10 个技能
# 自动淘汰最旧的，控制内存使用
```

## 🛠️ 高级用法

### 1. 动态加载多个技能

```python
# 一次性加载多个技能
skills_to_load = ["calculator", "web_scraper"]

for skill_name in skills_to_load:
    tools = loader.load_skill_tools(skill_name)
    # 使用工具...
```

### 2. 检查技能是否有工具

```python
metadata = loader.get_skill_metadata("calculator")

if metadata and metadata.get("has_tools"):
    tools = loader.load_skill_tools("calculator")
    # 执行工具...
```

### 3. 自定义工具执行

```python
from langchain_core.tools import StructuredTool

# 创建自定义工具
def my_custom_function(arg1: str, arg2: int) -> str:
    return f"处理: {arg1}, {arg2}"

custom_tool = StructuredTool(
    name="custom_tool",
    description="自定义工具",
    func=my_custom_function,
)

# 使用工具
result = custom_tool.invoke({"arg1": "test", "arg2": 42})
```

## 🔍 调试技巧

### 查看工具定义

```python
tools = loader.load_skill_tools("calculator")

for tool in tools:
    print(f"工具名: {tool.name}")
    print(f"描述: {tool.description}")
    print(f"参数: {tool.args_schema.schema()}")
    print()
```

### 测试工具执行

```python
# 直接测试工具
tools = loader.load_skill_tools("calculator")
calc_tool = next(t for t in tools if t.name == "calculate")

# 测试不同输入
test_cases = [
    "1 + 1",
    "10 * 5",
    "(3 + 4) * 2"
]

for expr in test_cases:
    result = calc_tool.invoke({"expression": expr})
    print(f"{expr} = {result}")
```

## 📚 完整示例

### Web 抓取示例

```yaml
# skills/web_scraper.yaml
name: web_scraper
description: Web 页面抓取技能
tools:
  - name: fetch_webpage
    description: 抓取网页内容
    parameters:
      url:
        type: string
        description: 网页 URL
    code: |
      import aiohttp
      import asyncio
      
      async def fetch():
          async with aiohttp.ClientSession() as session:
              async with session.get(url) as response:
                  return await response.text()
      
      return asyncio.run(fetch())
```

### 使用

```python
# 用户: 抓取 https://example.com 的内容
# Agent 自动调用:
invoke_skill_tool(
    skill_name="web_scraper",
    tool_name="fetch_webpage",
    url="https://example.com"
)
```

## 🎉 总结

### 核心优势

| 特性 | 说明 |
|------|------|
| ✅ **可执行工具** | 技能包含实际可执行的代码 |
| ✅ **按需加载** | 避免工具列表积累 |
| ✅ **LRU 缓存** | 自动管理内存 |
| ✅ **易于扩展** | 创建 YAML 文件即可 |
| ✅ **安全隔离** | 工具在独立环境执行 |

### 适用场景

- 📊 数据处理（计算器、转换器）
- 🌐 Web 抓取（页面抓取、API 调用）
- 🛠️ 工具集成（文件操作、系统命令）
- 📝 文本处理（格式化、转换）

**开始创建您的第一个带工具的技能吧！** 🚀
