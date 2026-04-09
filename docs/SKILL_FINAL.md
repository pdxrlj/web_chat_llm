# Skill 系统最终设计

## 📁 目录结构

```
skills/
└── web_scraper/          # 技能名称
    ├── __init__.py       # 工具实现（Python 代码）
    └── skill.yaml        # 技能配置（元数据 + 工具定义）
```

## ✅ 核心优势

| 特性 | 说明 |
|------|------|
| ✅ **代码与配置分离** | Python 代码在 `.py` 文件，配置在 `.yaml` 文件 |
| ✅ **易于维护** | IDE 提供完整支持（语法高亮、自动补全、类型检查） |
| ✅ **便于测试** | 可以单独测试工具函数 |
| ✅ **避免工具积累** | 按需加载，不预注册所有工具 |
| ✅ **LRU 缓存** | 自动管理内存 |

## 📝 创建新技能

### 1. 创建目录

```bash
mkdir skills/my_skill
```

### 2. 编写工具实现

```python
# skills/my_skill/__init__.py

def my_tool(arg1: str) -> str:
    """
    我的工具
    
    Args:
        arg1: 参数说明
    
    Returns:
        处理结果
    """
    return f"处理: {arg1}"
```

### 3. 编写技能配置

```yaml
# skills/my_skill/skill.yaml

name: my_skill
description: 我的自定义技能
version: 1.0.0
tags:
  - custom

# 技能指导
content: |
  这是技能的使用指导...

# 工具定义
tools:
  - name: my_tool
    description: 工具描述
    module: my_skill          # 模块名（文件夹名）
    function: my_tool         # 函数名
    parameters:
      arg1:
        type: string
        description: 参数说明
```

## 🚀 使用方式

### Agent 自动调用

```
用户: 抓取 https://example.com 的内容
Agent: [调用 list_skills] 发现 web_scraper 技能
       [调用 invoke_skill_tool("web_scraper", "fetch_webpage", 
                                url="https://example.com")]
       返回: 成功抓取，内容长度: 1234 字符...
```

### 手动测试

```python
from core.nl_chat.skill_loader import SkillLoader

loader = SkillLoader("./skills")

# 加载工具
tools = loader.load_skill_tools("web_scraper")

# 执行工具
tool = tools[0]
result = tool.invoke({"url": "https://example.com"})
print(result)
```

## 🔧 工具参数类型

| 类型 | 说明 | 示例 |
|------|------|------|
| `string` | 字符串 | `"hello"` |
| `number` | 数字 | `3.14` |
| `integer` | 整数 | `42` |
| `boolean` | 布尔值 | `true` |
| `array` | 数组 | `[1, 2, 3]` |

## ⚡ 性能优势

| 指标 | 传统方式 | 本方案 |
|------|---------|--------|
| **工具数量** | 持续增长 | 固定（3个工具） |
| **内存占用** | 高 | LRU 缓存控制 |
| **加载方式** | 预加载所有 | 按需加载 |
| **维护难度** | 高（代码在 YAML） | 低（代码在 .py） |

## 📊 测试结果

```
✅ 成功列出技能
✅ 成功加载技能内容
✅ 成功加载技能工具（找到 2 个工具）
✅ 工具执行正常
```

## 🎯 示例：web_scraper

查看 `skills/web_scraper/` 了解完整实现。

### 文件结构

```
skills/web_scraper/
├── __init__.py        # fetch_webpage, extract_text 函数
└── skill.yaml         # 技能配置
```

### 工具函数

```python
# skills/web_scraper/__init__.py

async def fetch_webpage(url: str, timeout: int = 10) -> str:
    """抓取网页内容"""
    import aiohttp
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=timeout) as response:
            return await response.text()

def extract_text(html: str) -> str:
    """从 HTML 中提取纯文本"""
    from bs4 import BeautifulSoup
    
    soup = BeautifulSoup(html, 'html.parser')
    return soup.get_text()
```

### 配置文件

```yaml
# skills/web_scraper/skill.yaml

name: web_scraper
description: Web 页面抓取技能
version: 1.0.0
tags:
  - web
  - scraper

content: |
  你可以使用 Web 抓取技能获取网页内容。

tools:
  - name: fetch_webpage
    description: 抓取网页内容
    module: web_scraper
    function: fetch_webpage
    parameters:
      url:
        type: string
        description: 网页 URL
      timeout:
        type: integer
        description: 超时时间（秒）
        default: 10

  - name: extract_text
    description: 从 HTML 中提取纯文本
    module: web_scraper
    function: extract_text
    parameters:
      html:
        type: string
        description: HTML 内容
```

## 🎉 总结

### 核心设计

```
代码实现（Python 文件）
    ↓ 模块导入
工具加载器
    ↓ 动态创建
LangChain 工具实例
    ↓ 按需调用
Agent 执行
```

### 关键改进

| 改进点 | 原方案 | 新方案 |
|--------|--------|--------|
| **代码位置** | YAML 内嵌 | Python 文件 |
| **维护性** | 难（无 IDE 支持） | 易（完整 IDE 支持） |
| **测试性** | 难（无法单独测试） | 易（可单元测试） |
| **复用性** | 低（代码不可复用） | 高（模块化） |
| **可读性** | 差（YAML 格式限制） | 好（Python 语法） |

**最佳实践：代码与配置分离，便于维护和测试！** 🚀
