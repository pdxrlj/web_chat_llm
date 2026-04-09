# 本地 Skill 系统

轻量级的本地技能加载系统，支持按需加载，不会导致工具积累。

## 🎯 核心特性

| 特性 | 说明 |
|------|------|
| ✅ **本地文件** | 从 YAML 文件加载，无需外部服务 |
| ✅ **按需加载** | 通过 `load_skill` 工具，需要时才加载 |
| ✅ **LRU 缓存** | 自动管理内存，避免积累 |
| ✅ **轻量级** | 只返回 prompt 内容，不注册工具实例 |

## 📁 目录结构

```
skills/                      # 技能目录
├── sql_expert.yaml         # SQL 专家
├── code_reviewer.yaml      # 代码审查
├── data_analyst.yaml       # 数据分析
└── README.md               # 文档

core/nl_chat/
├── skill_loader.py         # 加载器
├── middlewares/
│   └── skill_middleware.py # 中间件
└── chat.py                 # 集成
```

## 🚀 使用方式

### 1. Agent 自动发现技能

```python
from core.nl_chat.chat import ChatAgent

# 初始化时自动加载 skills/
agent = ChatAgent()

# Agent 自动获得两个工具：
# - list_skills: 列出所有技能
# - load_skill: 加载技能内容
```

### 2. 用户对话示例

```
用户: 帮我审查这段代码
Agent: [调用 list_skills] 发现 code_reviewer 技能
       [调用 load_skill("code_reviewer")] 加载技能内容
       [根据技能指导审查代码]
```

### 3. 创建新技能

在 `skills/` 目录创建 YAML 文件：

```yaml
# skills/my_skill.yaml
name: my_skill
description: 我的自定义技能
version: 1.0.0
tags:
  - custom
  - example

content: |
  你是 [技能名称] 专家...
  
  ## 核心能力
  - 能力 1
  - 能力 2
  
  ## 使用指南
  具体说明...
```

重启或重新加载：

```python
agent.skill_loader.reload_skills()
```

## 🔧 如何避免工具积累

### 问题分析

| 方案 | 是否积累 | 原因 |
|------|---------|------|
| ❌ 每个技能注册为工具 | 会 | 工具列表持续增长 |
| ❌ 预加载所有技能 | 会 | 内存占用增加 |
| ✅ **按需加载（本方案）** | **不会** | 只加载 prompt，不注册工具 |

### 核心原理

```
传统方式（会积累）:
Skill -> Tool Instance -> Agent.tools[]
           ↑ 每次都创建新实例

本方案（不会积累）:
Skill -> Prompt Content -> 临时使用
         ↑ 返回字符串，不创建实例
```

### 实现细节

```python
@tool
def load_skill(skill_name: str) -> str:
    """加载技能内容"""
    # 返回的是字符串（prompt）
    # 不是工具实例
    return skill_loader.load_skill(skill_name)
```

**关键点**：
- `load_skill` 返回字符串，不返回工具
- Agent 根据字符串内容临时获得能力
- 不需要在 `agent.tools` 中注册新工具
- LRU 缓存自动管理内存

## 📊 性能对比

| 指标 | 传统方式 | 本方案 |
|------|---------|--------|
| **内存占用** | 高（每个技能注册工具） | 低（只缓存字符串） |
| **初始化时间** | 长（加载所有工具） | 短（延迟加载） |
| **工具数量** | 持续增长 | 固定（2个工具） |
| **扩展性** | 差（工具过多影响性能） | 好（无上限） |

## 🎓 最佳实践

### 1. Skill 内容设计

```yaml
content: |
  你是专家，具备以下能力：
  
  ## 核心技能
  - 具体能力 1
  - 具体能力 2
  
  ## 使用指南
  1. 第一步...
  2. 第二步...
  
  ## 注意事项
  - 注意点 1
  - 注意点 2
```

### 2. 缓存大小设置

```python
# 根据项目规模调整
loader = SkillLoader(
    skills_dir="./skills",
    cache_size=10  # 默认缓存 10 个技能
)
```

### 3. 技能分类

使用标签便于管理：

```yaml
tags:
  - sql          # 类别：数据库
  - database     # 类别：数据库
  - optimization # 特性：优化
```

## 🔄 工作流程

```
1. Agent 初始化
   └─> 扫描 skills/ 目录
   └─> 创建索引（name -> file_path）

2. 用户提问
   └─> Agent 分析问题
   └─> 决定是否需要技能

3. 加载技能（如需要）
   └─> 调用 list_skills 查看可用技能
   └─> 调用 load_skill 加载具体技能
   └─> 根据技能内容回答问题

4. 缓存管理
   └─> LRU 自动淘汰最旧缓存
   └─> 控制内存使用
```

## 📝 示例场景

### SQL 查询场景

```
用户: 帮我优化这个 SQL 查询
Agent: [发现 SQL 相关问题]
       [调用 load_skill("sql_expert")]
       [加载 SQL 专家技能]
       [提供优化建议]
```

### 代码审查场景

```
用户: 审查一下这段 Python 代码
Agent: [发现代码审查需求]
       [调用 load_skill("code_reviewer")]
       [加载代码审查技能]
       [提供专业审查报告]
```

## 🛠️ 扩展开发

### 添加技能元数据

```yaml
name: skill_name
description: 技能描述
version: 1.0.0
author: Your Name
tags: [tag1, tag2]
priority: 10  # 优先级（可选）
dependencies:  # 依赖（可选）
  - another_skill
```

### 自定义加载逻辑

```python
from core.nl_chat.skill_loader import SkillLoader

class CustomSkillLoader(SkillLoader):
    def load_skill(self, skill_name: str):
        # 自定义加载逻辑
        # 例如：从数据库加载、API 获取等
        content = super().load_skill(skill_name)
        
        # 后处理
        if content:
            content = self._post_process(content)
        
        return content
```

## ⚡ 性能优化

### 1. 预热缓存

```python
# 初始化时预加载常用技能
common_skills = ["sql_expert", "code_reviewer"]
for skill in common_skills:
    loader.load_skill(skill)
```

### 2. 异步加载

```python
import asyncio

async def load_skills_async(skill_names):
    tasks = [
        asyncio.to_thread(loader.load_skill, name)
        for name in skill_names
    ]
    return await asyncio.gather(*tasks)
```

## 📚 参考资料

- [LangChain 官方 Skill 系统](https://docs.langchain.com/oss/python/langchain/multi-agent/skills)
- [Model Context Protocol (MCP)](https://modelcontextprotocol.io/)
- 项目文档: `skills/README.md`

## 🤝 贡献

欢迎添加更多技能！

1. 在 `skills/` 创建 YAML 文件
2. 遵循标准格式
3. 提交 PR

## 📄 许可证

MIT License
