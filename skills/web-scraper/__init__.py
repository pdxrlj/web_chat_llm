"""Web Scraper Skill - 生产级网页抓取工具

功能特性：
- 连接池管理和复用
- 自动重试机制
- 速率限制（令牌桶算法）
- 超时控制
- 代理支持
- 内容大小限制
- URL 验证
- HTML 解析和文本提取
- 元数据提取

使用示例：
    ```python
    from skills.web_scraper import fetch_webpage, extract_text
    
    # 抓取网页
    html = await fetch_webpage("https://example.com")
    
    # 提取文本
    text = extract_text(html)
    ```

环境变量配置：
    - WEB_SCRAPER_CONNECT_TIMEOUT: 连接超时（秒）
    - WEB_SCRAPER_READ_TIMEOUT: 读取超时（秒）
    - WEB_SCRAPER_MAX_RETRIES: 最大重试次数
    - WEB_SCRAPER_PROXY: 代理地址
    - WEB_SCRAPER_REQUESTS_PER_SECOND: 每秒最大请求数
"""

import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from .config import ScraperConfig
from .client import HTTPClient
from .utils import (
    validate_url,
    extract_text_from_html,
    extract_links_from_html,
    extract_metadata_from_html,
    is_content_type_allowed
)
from .exceptions import (
    ScraperException,
    URLValidationError,
    NetworkError,
    TimeoutError,
    RateLimitError,
    ContentTooLargeError,
    RetryExhaustedError
)


logger = logging.getLogger(__name__)


# 全局客户端实例（延迟初始化）
_client: Optional[HTTPClient] = None


async def get_client() -> HTTPClient:
    """获取全局客户端实例（单例模式）"""
    global _client
    if _client is None or _client._closed:
        config = ScraperConfig.from_env()
        _client = HTTPClient(config)
        await _client.start()
    return _client


async def close_client() -> None:
    """关闭全局客户端"""
    global _client
    if _client:
        await _client.close()
        _client = None


@dataclass
class ScraperResult:
    """抓取结果"""
    url: str
    status_code: int
    content: str
    content_length: int
    headers: Dict[str, str]
    metadata: Dict[str, str]
    
    def __str__(self) -> str:
        return (
            f"URL: {self.url}\n"
            f"状态码: {self.status_code}\n"
            f"内容长度: {self.content_length} 字符\n"
            f"标题: {self.metadata.get('title', 'N/A')}\n"
        )


async def fetch_webpage(
    url: str,
    timeout: Optional[int] = None,
    headers: Optional[Dict[str, str]] = None,
    extract_metadata: bool = True
) -> str:
    """抓取网页内容
    
    功能：
    - 自动 URL 验证
    - 自动重试（3次）
    - 速率限制（2 req/s）
    - 超时控制（60秒）
    - 内容大小限制（10MB）
    
    Args:
        url: 网页 URL（支持自动添加 https://）
        timeout: 超时时间（秒），None 使用默认配置
        headers: 自定义请求头
        extract_metadata: 是否提取元数据
    
    Returns:
        抓取结果信息（包含 URL、状态码、内容等）
    
    Raises:
        URLValidationError: URL 格式不正确
        NetworkError: 网络错误
        TimeoutError: 请求超时
        RateLimitError: 请求过于频繁
        ContentTooLargeError: 内容过大
        RetryExhaustedError: 重试次数耗尽
    
    Example:
        ```python
        result = await fetch_webpage("example.com")
        print(result)
        ```
    """
    try:
        # 验证 URL
        url = validate_url(url)
        
        # 获取客户端
        client = await get_client()
        
        # 覆盖超时配置
        config = None
        if timeout:
            config = ScraperConfig.from_env()
            config.total_timeout = timeout
            client = HTTPClient(config)
            await client.start()
        
        # 发起请求
        logger.info(f"开始抓取: {url}")
        html = await client.get(url, headers=headers, raise_for_status=True)
        
        # 提取元数据
        metadata = {}
        if extract_metadata:
            try:
                metadata = extract_metadata_from_html(html)
            except Exception as e:
                logger.warning(f"提取元数据失败: {e}")
        
        result = (
            f"✅ 成功抓取\n"
            f"URL: {url}\n"
            f"内容长度: {len(html)} 字符\n"
        )
        
        if title := metadata.get("title"):
            result += f"标题: {title}\n"
        
        if desc := metadata.get("description"):
            result += f"描述: {desc[:100]}...\n"
        
        result += f"\n前 500 字符:\n{html[:500]}"
        
        logger.info(f"抓取成功: {url} ({len(html)} 字符)")
        return result
    
    except ScraperException:
        raise
    except Exception as e:
        logger.error(f"抓取失败: {url} - {str(e)}")
        raise NetworkError(f"抓取失败: {str(e)}", url=url) from e


def extract_text(
    html: str,
    max_length: int = 10000,
    remove_scripts: bool = True,
    remove_styles: bool = True
) -> str:
    """从 HTML 提取纯文本
    
    功能：
    - 移除脚本和样式
    - 移除注释
    - 清理空白
    - 限制文本长度
    
    Args:
        html: HTML 内容
        max_length: 最大文本长度
        remove_scripts: 是否移除脚本
        remove_styles: 是否移除样式
    
    Returns:
        提取的纯文本
    
    Example:
        ```python
        text = extract_text(html, max_length=5000)
        ```
    """
    try:
        logger.info(f"开始提取文本，HTML 长度: {len(html)}")
        
        text = extract_text_from_html(
            html,
            max_length=max_length,
            remove_scripts=remove_scripts,
            remove_styles=remove_styles
        )
        
        result = (
            f"✅ 文本提取成功\n"
            f"HTML 长度: {len(html)} 字符\n"
            f"文本长度: {len(text)} 字符\n"
            f"\n内容:\n{text}"
        )
        
        logger.info(f"文本提取成功: {len(text)} 字符")
        return result
    
    except ImportError as e:
        logger.error(f"缺少依赖: {e}")
        return f"❌ 错误: {str(e)}"
    except Exception as e:
        logger.error(f"文本提取失败: {str(e)}")
        return f"❌ 提取失败: {str(e)}"


def extract_links(html: str, base_url: Optional[str] = None) -> str:
    """从 HTML 提取链接
    
    Args:
        html: HTML 内容
        base_url: 基础 URL（用于解析相对链接）
    
    Returns:
        链接列表（格式化字符串）
    """
    try:
        logger.info(f"开始提取链接，HTML 长度: {len(html)}")
        
        links = extract_links_from_html(html, base_url)
        
        if not links:
            return "❌ 未找到链接"
        
        result = f"✅ 找到 {len(links)} 个链接:\n\n"
        
        for i, link in enumerate(links[:20], 1):  # 只显示前 20 个
            result += f"{i}. {link['text']}\n   {link['url']}\n\n"
        
        if len(links) > 20:
            result += f"... 还有 {len(links) - 20} 个链接\n"
        
        logger.info(f"链接提取成功: {len(links)} 个")
        return result
    
    except Exception as e:
        logger.error(f"链接提取失败: {str(e)}")
        return f"❌ 提取失败: {str(e)}"


# 导出公共 API
__all__ = [
    # 配置
    "ScraperConfig",
    # 客户端
    "HTTPClient",
    "get_client",
    "close_client",
    # 主要功能
    "fetch_webpage",
    "extract_text",
    "extract_links",
    # 工具函数
    "validate_url",
    "extract_text_from_html",
    "extract_links_from_html",
    "extract_metadata_from_html",
    # 异常
    "ScraperException",
    "URLValidationError",
    "NetworkError",
    "TimeoutError",
    "RateLimitError",
    "ContentTooLargeError",
    "RetryExhaustedError",
    # 结果类型
    "ScraperResult",
]
