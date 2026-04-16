"""网络搜索工具，基于 SearXNG 实例。

参考 langchain-community SearxSearchWrapper 的设计模式：
- 支持 categories / engines 过滤
- 支持 time_range 时间范围
- 多种结果格式（snippet / document）
- 漂亮的日志输出
"""

import aiohttp
from langchain_core.tools import tool

from core.config import config
from core.logger import setup_logger

logger = setup_logger(__name__)


def _format_results(results: list[dict], max_results: int) -> str:
    """将 SearXNG JSON 结果格式化为可读文本（供 LLM 消费）。"""
    if not results:
        return "未找到相关结果"

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

    return "\n\n".join(items)


@tool
async def web_search(
    query: str,
    categories: str = "",
    engines: str = "",
    time_range: str = "",
) -> str:
    """搜索互联网获取最新信息。当需要查找实时资讯、事实、数据或用户提问涉及近期事件时使用此工具。

    Args:
        query: 搜索关键词
        categories: 搜索分类，逗号分隔，如 "general,news,images"。留空为全部分类
        engines: 指定搜索引擎，逗号分隔，如 "google,bing,wikipedia"。留空使用默认引擎
        time_range: 时间范围过滤，可选值: day / month / year。留空不限制

    Returns:
        搜索结果摘要文本
    """
    search_cfg = config.tools.search
    if not search_cfg.url:
        return "搜索服务未配置"

    params: dict[str, str | int] = {
        "q": query,
        "format": "json",
        "language": search_cfg.language,
    }
    if categories:
        params["categories"] = categories
    if engines:
        params["engines"] = engines
    if time_range:
        params["time_range"] = time_range

    headers: dict[str, str] = {}
    # SearXNG secret_key 用于 limiter token 认证（如服务端开启了 limiter）
    if search_cfg.api_key:
        headers["Authorization"] = f"Bearer {search_cfg.api_key}"

    logger.info(
        f"🔍 搜索请求: query=\"{query}\", categories={categories or 'all'}, engines={engines or 'default'}, time_range={time_range or 'none'}"
    )

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
                    logger.error(f"搜索请求失败 status={resp.status} body={text[:200]}")
                    return f"搜索请求失败，状态码: {resp.status}"
                data = await resp.json(content_type=None)
    except aiohttp.ClientError as e:
        logger.error(f"搜索网络异常: {e}")
        return f"搜索网络异常: {e}"
    except Exception as e:
        logger.error(f"搜索请求异常: {e}")
        return f"搜索请求异常: {e}"

    results = data.get("results", [])
    number_of_results = data.get("number_of_results", 0)
    max_results = search_cfg.max_results

    # 漂亮打印搜索结果摘要
    logger.info(
        f"🔍 搜索完成: 返回 {len(results)} 条结果"
        f"{f' (总约 {number_of_results} 条)' if number_of_results else ''},"
        f" 取前 {min(len(results), max_results)} 条"
    )
    for i, r in enumerate(results[:max_results]):
        title = r.get("title", "无标题")
        url = r.get("url", "")
        engine = r.get("engine", "")
        score = r.get("score", 0)
        logger.info(f"  [{i + 1}] {title}")
        logger.info(f"      {url}")
        logger.info(f"      引擎: {engine} | 相关度: {score:.1f}")

    return _format_results(results, max_results)
