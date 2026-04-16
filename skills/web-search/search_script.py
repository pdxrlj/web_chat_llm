#!/usr/bin/env python3
"""
网络搜索脚本（基于 SearXNG）

使用方式：
    uv run skills/web-search/search_script.py "搜索关键词"
    uv run skills/web-search/search_script.py "科技新闻" --categories news
    uv run skills/web-search/search_script.py "今日新闻" --time_range day
"""

import argparse
import asyncio
import json
import os
import sys

# Windows 控制台 UTF-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

# 从项目根目录加载配置
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_sys_path = _project_root
if _sys_path not in sys.path:
    sys.path.insert(0, _sys_path)

from core.config import config


def _get_search_cfg():
    """获取搜索配置"""
    return config.tools.search


async def search(query: str, categories: str = "", time_range: str = "", engines: str = "baidu") -> str:
    """执行搜索请求"""
    import aiohttp

    search_cfg = _get_search_cfg()
    if not search_cfg.url:
        return "错误: 搜索服务未配置"

    params: dict[str, str | int] = {
        "q": query,
        "format": "json",
        "language": search_cfg.language,
    }
    if categories:
        params["categories"] = categories
    if time_range:
        params["time_range"] = time_range
    if engines:
        params["engines"] = engines

    headers: dict[str, str] = {}
    if search_cfg.api_key:
        headers["Authorization"] = f"Bearer {search_cfg.api_key}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                search_cfg.url + "/search",
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    return f"搜索请求失败，状态码: {resp.status}"
                data = await resp.json(content_type=None)
    except Exception as e:
        return f"搜索请求异常: {e}"

    results = data.get("results", [])
    if not results:
        return "未找到相关结果"

    max_results = search_cfg.max_results
    items: list[str] = []
    for i, r in enumerate(results[:max_results]):
        title = r.get("title", "无标题")
        url = r.get("url", "")
        snippet = r.get("content", "")
        engine = r.get("engine", "")
        score = r.get("score", 0)

        parts = [f"【{i + 1}】{title}"]
        if snippet:
            parts.append(f"    {snippet}")
        parts.append(f"    来源: {url}")
        if engine:
            parts.append(f"    引擎: {engine} | 相关度: {score:.1f}")
        items.append("\n".join(parts))

    total = data.get("number_of_results", 0)
    header = f"搜索 '{query}' 返回 {len(results)} 条结果"
    if total:
        header += f" (总约 {total} 条)"
    header += f"，取前 {min(len(results), max_results)} 条：\n"

    return header + "\n\n".join(items)


def main():
    parser = argparse.ArgumentParser(description="网络搜索（SearXNG）")
    parser.add_argument("query", help="搜索关键词")
    parser.add_argument("--categories", default="", help="搜索分类，如 general,news,images")
    parser.add_argument("--time_range", default="", choices=["day", "month", "year"], help="时间范围")
    parser.add_argument("--engines", default="baidu", help="指定搜索引擎，如 baidu,bing,google（逗号分隔），默认baidu")
    args = parser.parse_args()

    result = asyncio.run(search(args.query, args.categories, args.time_range, args.engines))
    print(result)


if __name__ == "__main__":
    main()
