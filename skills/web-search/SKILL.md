---
name: web-search
description: >
  当用户询问实时信息、最新资讯、天气、新闻、股价、汇率、赛事结果等需要互联网搜索的问题时使用此技能。
  Use this skill whenever the user asks for 天气、新闻、最新、实时、搜索、search、
  what is the weather, latest news, current events, search the web.
---

# 网络搜索

当用户询问需要实时互联网信息的问题时，使用本技能。

## 如何使用

使用 `shell_execute` 工具执行以下命令来搜索互联网：
**注意：shell_execute 的 timeout 参数单独设置即可，不要在命令中添加 --timeout 等额外参数。**

```
uv run skills/web-search/search_script.py "搜索关键词"
```

### 步骤

1. 从用户问题中提取搜索关键词
2. 使用 `shell_execute` 工具执行搜索命令
3. 将搜索结果以自然、简洁的方式告诉用户

### 命令说明

| 命令 | 说明 | 示例 |
|------|------|------|
| 默认搜索 | 搜索互联网并返回结果摘要 | `uv run skills/web-search/search_script.py "合肥天气"` |
| 指定分类 | 按分类搜索（news/general/images等） | `uv run skills/web-search/search_script.py "科技新闻" --categories news` |
| 时间范围 | 限定时间范围（day/month/year） | `uv run skills/web-search/search_script.py "今日新闻" --time_range day` |

### 示例

用户问 "合肥今天天气怎么样"：
- 调用 `shell_execute`，命令为：`uv run skills/web-search/search_script.py "合肥天气 今天"`
- 将搜索结果总结后告诉用户

用户问 "最近有什么科技新闻"：
- 调用 `shell_execute`，命令为：`uv run skills/web-search/search_script.py "最新科技新闻" --time_range day`
- 将新闻摘要整理后告诉用户

## 注意事项

- 搜索关键词应精炼，提取用户问题中的核心词
- 搜索结果可能包含多条，请提炼最相关的信息回复用户
- 不要原样复制搜索结果，用自然语言总结
- **只搜索一次！** 搜索返回的是网页摘要，不是完整页面内容，这是正常的。根据第一次搜索结果即可总结回答用户，绝对不要为了获取更精确的结果而反复换关键词重新搜索
- 只有当搜索返回 0 条结果时，才可以换一组关键词再搜索一次

## 深入获取网页内容

搜索结果只包含网页摘要，如果需要获取某个网页的完整内容，可以再调用 web-scraper 技能：

1. 先调用 `activate_skill` 加载 web-scraper 技能
2. 使用 `shell_execute` 执行：`uv run skills/web-scraper/scraper_script.py text "网页URL"`

例如搜索后发现了天气网页 `https://www.weather.com.cn/weather/101220101.shtml`，想获取详细天气：
- 调用 `activate_skill`，name 为 `web-scraper`
- 调用 `shell_execute`，命令为：`uv run skills/web-scraper/scraper_script.py text "https://www.weather.com.cn/weather/101220101.shtml"`
- 只抓取最相关的 1 个网页即可，不要批量抓取
