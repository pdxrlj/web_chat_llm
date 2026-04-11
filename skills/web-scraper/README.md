# Web Scraper Skill

生产级网页抓取工具，专为高并发、高可靠性场景设计。

## 🚀 功能特性

### 核心能力
- ✅ **网页抓取** - 支持 HTTP/HTTPS，自动重定向
- ✅ **文本提取** - 从 HTML 提取纯文本，自动清理
- ✅ **链接提取** - 提取页面中的所有链接
- ✅ **元数据提取** - 提取标题、描述、关键词等

### 生产级特性
- ✅ **连接池管理** - 复用连接，提升性能
- ✅ **自动重试** - 3次重试，指数退避策略
- ✅ **速率限制** - 令牌桶算法，避免被封禁
- ✅ **超时控制** - 多级超时（连接、读取、总超时）
- ✅ **代理支持** - HTTP/HTTPS 代理
- ✅ **内容限制** - 防止内存溢出（最大 10MB）
- ✅ **URL 验证** - 自动补全协议，验证格式
- ✅ **异常处理** - 详细的错误信息和异常类型

## 📦 安装

```bash
pip install aiohttp beautifulsoup4 lxml
```

## 🔧 配置

### 方式 1: 环境变量（推荐）

```bash
# 超时配置
export WEB_SCRAPER_CONNECT_TIMEOUT=10
export WEB_SCRAPER_READ_TIMEOUT=30
export WEB_SCRAPER_TOTAL_TIMEOUT=60

# 重试配置
export WEB_SCRAPER_MAX_RETRIES=3
export WEB_SCRAPER_RETRY_DELAY=1.0

# 连接池配置
export WEB_SCRAPER_MAX_CONNECTIONS=100

# 代理配置
export WEB_SCRAPER_PROXY=http://proxy.example.com:8080

# 速率限制
export WEB_SCRAPER_REQUESTS_PER_SECOND=2.0

# 内容限制
export WEB_SCRAPER_MAX_CONTENT_LENGTH=10485760  # 10MB
```

### 方式 2: 代码配置

```python
from skills.web_scraper import ScraperConfig, HTTPClient

# 创建自定义配置
config = ScraperConfig(
    connect_timeout=10,
    read_timeout=30,
    max_retries=3,
    requests_per_second=5.0,
    proxy="http://proxy.example.com:8080"
)

# 使用配置创建客户端
client = HTTPClient(config)
```

## 📖 使用指南

### 1. 基础用法

```python
import asyncio
from skills.web_scraper import fetch_webpage, extract_text

async def main():
    # 抓取网页
    result = await fetch_webpage("https://example.com")
    print(result)
    
    # 提取文本
    text = extract_text(html, max_length=5000)
    print(text)

asyncio.run(main())
```

### 2. 高级用法

```python
import asyncio
from skills.web_scraper import HTTPClient, ScraperConfig

async def main():
    # 自定义配置
    config = ScraperConfig(
        max_retries=5,
        requests_per_second=5.0,
        proxy="http://localhost:7890"
    )
    
    # 使用上下文管理器
    async with HTTPClient(config) as client:
        html = await client.get("https://example.com")
        print(f"内容长度: {len(html)}")

asyncio.run(main())
```

### 3. 流式读取（大文件）

```python
import asyncio
from skills.web_scraper import HTTPClient

async def main():
    client = HTTPClient()
    await client.start()
    
    try:
        async with client.get_stream("https://example.com/large-file") as response:
            async for chunk in response.content.iter_chunked(8192):
                # 处理每个块
                print(f"收到 {len(chunk)} 字节")
    finally:
        await client.close()

asyncio.run(main())
```

### 4. 批量抓取

```python
import asyncio
from skills.web_scraper import get_client, close_client

async def fetch_batch(urls: list[str]):
    client = await get_client()
    
    try:
        # 并发抓取（自动速率限制）
        tasks = [client.get(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for url, result in zip(urls, results):
            if isinstance(result, Exception):
                print(f"❌ {url}: {result}")
            else:
                print(f"✅ {url}: {len(result)} 字符")
    finally:
        await close_client()

# 运行
urls = [
    "https://example.com/page1",
    "https://example.com/page2",
    "https://example.com/page3"
]

asyncio.run(fetch_batch(urls))
```

### 5. 错误处理

```python
import asyncio
from skills.web_scraper import (
    fetch_webpage,
    NetworkError,
    TimeoutError,
    RateLimitError,
    ContentTooLargeError
)

async def main():
    try:
        result = await fetch_webpage("https://example.com")
    except TimeoutError as e:
        print(f"请求超时: {e}")
    except RateLimitError as e:
        print(f"请求过于频繁，请 {e.retry_after} 秒后重试")
    except ContentTooLargeError as e:
        print(f"内容过大: {e.content_length} > {e.max_length}")
    except NetworkError as e:
        print(f"网络错误: {e}")

asyncio.run(main())
```

## 🛠️ API 参考

### `fetch_webpage(url, timeout=None, headers=None, extract_metadata=True)`

抓取网页内容。

**参数:**
- `url` (str): 网页 URL
- `timeout` (int, optional): 超时时间（秒）
- `headers` (dict, optional): 自定义请求头
- `extract_metadata` (bool): 是否提取元数据

**返回:** `str` - 抓取结果信息

### `extract_text(html, max_length=10000, remove_scripts=True, remove_styles=True)`

从 HTML 提取纯文本。

**参数:**
- `html` (str): HTML 内容
- `max_length` (int): 最大文本长度
- `remove_scripts` (bool): 是否移除脚本
- `remove_styles` (bool): 是否移除样式

**返回:** `str` - 提取的文本

### `extract_links(html, base_url=None)`

从 HTML 提取链接。

**参数:**
- `html` (str): HTML 内容
- `base_url` (str, optional): 基础 URL

**返回:** `str` - 链接列表（格式化字符串）

## 📊 性能特性

| 特性 | 配置 | 说明 |
|------|------|------|
| 连接池 | 100 连接 | 复用 TCP 连接 |
| 每主机限制 | 10 连接 | 避免对单主机过大压力 |
| 重试次数 | 3 次 | 指数退避策略 |
| 速率限制 | 2 req/s | 令牌桶算法 |
| 超时时间 | 60 秒 | 连接+读取总和 |
| 最大内容 | 10 MB | 防止内存溢出 |

## 🔍 最佳实践

### 1. 遵守 robots.txt

```python
# TODO: 实现 robots.txt 检查
```

### 2. 设置合理的 User-Agent

```python
from skills.web_scraper import ScraperConfig

config = ScraperConfig(
    user_agent="MyBot/1.0 (contact@example.com)"
)
```

### 3. 使用速率限制

```python
config = ScraperConfig(
    requests_per_second=1.0,  # 1 req/s
    burst_size=3  # 允许短暂突发
)
```

### 4. 错误处理

```python
from skills.web_scraper import ScraperException

try:
    result = await fetch_webpage(url)
except ScraperException as e:
    logger.error(f"抓取失败: {e}", exc_info=True)
```

### 5. 资源清理

```python
# 使用上下文管理器自动清理
async with HTTPClient() as client:
    html = await client.get(url)

# 或手动清理
client = HTTPClient()
try:
    await client.start()
    html = await client.get(url)
finally:
    await client.close()
```

## 🐛 故障排查

### 问题 1: ImportError: beautifulsoup4

```bash
pip install beautifulsoup4 lxml
```

### 问题 2: 请求超时

增加超时时间：
```bash
export WEB_SCRAPER_TOTAL_TIMEOUT=120
```

### 问题 3: 被网站封禁

降低速率：
```bash
export WEB_SCRAPER_REQUESTS_PER_SECOND=0.5
```

使用代理：
```bash
export WEB_SCRAPER_PROXY=http://proxy.example.com:8080
```

### 问题 4: 内存不足

降低内容限制：
```bash
export WEB_SCRAPER_MAX_CONTENT_LENGTH=1048576  # 1MB
```

## 📝 更新日志

### v2.0.0 (2026-04-09)
- 🎉 重构为生产级架构
- ✨ 新增连接池管理
- ✨ 新增自动重试机制
- ✨ 新增速率限制（令牌桶）
- ✨ 新增代理支持
- ✨ 新增详细的异常体系
- ✨ 新增元数据提取
- ✨ 新增链接提取
- 🐛 修复内存泄漏问题
- 📚 完善文档和示例

### v1.0.0
- 基础网页抓取功能

## 📄 License

MIT License

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！
