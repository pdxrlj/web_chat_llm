---
name: web-scraper
description: >
  当用户需要抓取网页内容、获取网页信息、提取网页文本或链接时使用此技能。
  Use this skill whenever the user asks for 抓取网页、获取网页内容、网页上有什么、
  web scraping, fetch webpage, extract text from HTML.
---

# Web 页面抓取

当用户需要获取网页内容时，使用本技能。

## 如何使用

使用 `shell_execute` 工具执行以下命令来抓取网页：

```
uv run skills/web-scraper/scraper_script.py <command> "URL"
```

### 步骤

1. 从用户问题中提取 URL
2. 使用 `shell_execute` 工具执行命令
3. 将结果以自然的方式告诉用户

### 命令说明

| 命令 | 说明 | 示例 |
|------|------|------|
| `fetch` | 抓取网页基本信息 | `uv run skills/web-scraper/scraper_script.py fetch "https://www.baidu.com"` |
| `text` | 抓取并提取纯文本 | `uv run skills/web-scraper/scraper_script.py text "https://www.baidu.com"` |
| `links` | 抓取并提取链接 | `uv run skills/web-scraper/scraper_script.py links "https://www.baidu.com"` |

### 示例

用户问 "www.baidu.com 这个网站有什么东西"：
- 调用 `shell_execute`，命令为：`uv run skills/web-scraper/scraper_script.py text "https://www.baidu.com"`
- 将提取的文本内容总结后告诉用户

用户问 "这个页面上有哪些链接 https://example.com"：
- 调用 `shell_execute`，命令为：`uv run skills/web-scraper/scraper_script.py links "https://example.com"`
- 将链接列表整理后告诉用户

## 注意事项

- URL 需要包含协议（https://），如果用户只给了域名，脚本会自动补全
- 注意用引号包裹 URL，避免 shell 特殊字符问题
- 抓取结果可能较长，请提炼关键信息回复用户
- 遵守网站使用条款，不要过度请求
