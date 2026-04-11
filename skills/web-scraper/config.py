"""Web Scraper 配置管理"""

from dataclasses import dataclass, field
from typing import Optional
import os


@dataclass
class ScraperConfig:
    """Web Scraper 配置
    
    可以通过环境变量覆盖默认配置
    """
    
    # 超时配置
    connect_timeout: int = 10  # 连接超时（秒）
    read_timeout: int = 30  # 读取超时（秒）
    total_timeout: int = 60  # 总超时（秒）
    
    # 重试配置
    max_retries: int = 3  # 最大重试次数
    retry_delay: float = 1.0  # 重试延迟（秒）
    retry_backoff: float = 2.0  # 重试退避系数
    
    # 并发配置
    max_connections: int = 100  # 最大连接数
    max_connections_per_host: int = 10  # 每个主机最大连接数
    
    # 请求配置
    user_agent: str = "Mozilla/5.0 (compatible; WebScraper/1.0)"
    follow_redirects: bool = True
    max_redirects: int = 10
    
    # 代理配置
    proxy: Optional[str] = None
    proxy_auth: Optional[str] = None
    
    # 速率限制
    requests_per_second: float = 2.0  # 每秒最大请求数
    burst_size: int = 5  # 突发请求大小
    
    # 内容限制
    max_content_length: int = 10 * 1024 * 1024  # 最大内容长度（10MB）
    max_text_length: int = 10000  # 最大文本长度
    
    @classmethod
    def from_env(cls) -> "ScraperConfig":
        """从环境变量加载配置
        
        环境变量格式：
        - WEB_SCRAPER_CONNECT_TIMEOUT
        - WEB_SCRAPER_READ_TIMEOUT
        - WEB_SCRAPER_MAX_RETRIES
        - WEB_SCRAPER_PROXY
        - 等
        """
        config = cls()
        
        # 超时配置
        if timeout := os.getenv("WEB_SCRAPER_CONNECT_TIMEOUT"):
            config.connect_timeout = int(timeout)
        if timeout := os.getenv("WEB_SCRAPER_READ_TIMEOUT"):
            config.read_timeout = int(timeout)
        if timeout := os.getenv("WEB_SCRAPER_TOTAL_TIMEOUT"):
            config.total_timeout = int(timeout)
        
        # 重试配置
        if retries := os.getenv("WEB_SCRAPER_MAX_RETRIES"):
            config.max_retries = int(retries)
        if delay := os.getenv("WEB_SCRAPER_RETRY_DELAY"):
            config.retry_delay = float(delay)
        
        # 连接池配置
        if max_conn := os.getenv("WEB_SCRAPER_MAX_CONNECTIONS"):
            config.max_connections = int(max_conn)
        
        # 代理配置
        if proxy := os.getenv("WEB_SCRAPER_PROXY"):
            config.proxy = proxy
        
        # 速率限制
        if rps := os.getenv("WEB_SCRAPER_REQUESTS_PER_SECOND"):
            config.requests_per_second = float(rps)
        
        # 内容限制
        if max_len := os.getenv("WEB_SCRAPER_MAX_CONTENT_LENGTH"):
            config.max_content_length = int(max_len)
        
        return config
    
    def to_client_kwargs(self) -> dict:
        """转换为 aiohttp.ClientSession 参数"""
        import aiohttp
        
        timeout = aiohttp.ClientTimeout(
            total=self.total_timeout,
            connect=self.connect_timeout,
            sock_read=self.read_timeout
        )
        
        connector = aiohttp.TCPConnector(
            limit=self.max_connections,
            limit_per_host=self.max_connections_per_host,
            ttl_dns_cache=300
        )
        
        return {
            "timeout": timeout,
            "connector": connector,
            "headers": {
                "User-Agent": self.user_agent
            }
        }
