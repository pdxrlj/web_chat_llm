"""HTTP 客户端封装"""

import asyncio
import logging
import time
from typing import Optional, Dict, AsyncIterator
from contextlib import asynccontextmanager
import aiohttp

from .config import ScraperConfig
from .exceptions import (
    NetworkError,
    TimeoutError,
    RateLimitError,
    ContentTooLargeError,
    RetryExhaustedError
)


logger = logging.getLogger(__name__)


class RateLimiter:
    """速率限制器（令牌桶算法）
    
    支持异步上下文管理器协议，可以使用 async with 语句
    """
    
    def __init__(self, rate: float, burst: int):
        self.rate = rate  # 令牌生成速率（令牌/秒）
        self.burst = burst  # 桶容量
        self.tokens = burst
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()
    
    async def __aenter__(self) -> "RateLimiter":
        """进入上下文管理器时获取令牌"""
        await self.acquire()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """退出上下文管理器（无需额外操作）"""
        pass
    
    async def acquire(self) -> None:
        """获取令牌"""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
            self.last_update = now
            
            if self.tokens < 1:
                sleep_time = (1 - self.tokens) / self.rate
                await asyncio.sleep(sleep_time)
                self.tokens = 0
            else:
                self.tokens -= 1


class RetryPolicy:
    """重试策略"""
    
    def __init__(self, max_retries: int, delay: float, backoff: float):
        self.max_retries = max_retries
        self.delay = delay
        self.backoff = backoff
    
    def should_retry(self, error: Exception) -> bool:
        """判断是否应该重试"""
        # 超时、连接错误、5xx 错误可以重试
        if isinstance(error, (TimeoutError, asyncio.TimeoutError)):
            return True
        if isinstance(error, aiohttp.ClientError):
            return True
        if isinstance(error, NetworkError) and error.status_code:
            return 500 <= error.status_code < 600
        return False
    
    async def wait(self, attempt: int) -> None:
        """等待重试"""
        wait_time = self.delay * (self.backoff ** (attempt - 1))
        logger.info(f"等待 {wait_time:.2f}秒后重试（第 {attempt} 次）")
        await asyncio.sleep(wait_time)


class HTTPClient:
    """HTTP 客户端（支持连接池、重试、速率限制）"""
    
    def __init__(self, config: Optional[ScraperConfig] = None):
        self.config = config or ScraperConfig.from_env()
        self._session: Optional[aiohttp.ClientSession] = None
        self._rate_limiter = RateLimiter(
            self.config.requests_per_second,
            self.config.burst_size
        )
        self._retry_policy = RetryPolicy(
            self.config.max_retries,
            self.config.retry_delay,
            self.config.retry_backoff
        )
        self._closed = False
    
    async def __aenter__(self) -> "HTTPClient":
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()
    
    async def start(self) -> None:
        """启动客户端"""
        if self._session is None or self._session.closed:
            kwargs = self.config.to_client_kwargs()
            
            # 添加代理配置
            if self.config.proxy:
                kwargs["proxy"] = self.config.proxy
            
            self._session = aiohttp.ClientSession(**kwargs)
            logger.info("HTTP 客户端已启动")
    
    async def close(self) -> None:
        """关闭客户端"""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.info("HTTP 客户端已关闭")
        self._closed = True
    
    @asynccontextmanager
    async def get_stream(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None
    ) -> AsyncIterator[aiohttp.ClientResponse]:
        """流式获取响应（上下文管理器）"""
        await self.start()
        
        # 类型断言：start() 已确保 _session 不为 None
        assert self._session is not None, "HTTP client not initialized"
        
        async with self._rate_limiter:
            try:
                async with self._session.get(
                    url,
                    headers=headers,
                    allow_redirects=self.config.follow_redirects,
                    max_redirects=self.config.max_redirects
                ) as response:
                    yield response
            except asyncio.TimeoutError as e:
                raise TimeoutError(
                    f"请求超时（{self.config.total_timeout}秒）",
                    url=url
                ) from e
            except aiohttp.ClientError as e:
                raise NetworkError(
                    f"网络请求失败: {str(e)}",
                    url=url
                ) from e
    
    async def get(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        raise_for_status: bool = True
    ) -> str:
        """获取网页内容（带重试）"""
        errors = []
        
        for attempt in range(1, self.config.max_retries + 1):
            try:
                return await self._get_once(url, headers, raise_for_status)
            except Exception as e:
                errors.append(e)
                
                if not self._retry_policy.should_retry(e):
                    raise
                
                if attempt < self.config.max_retries:
                    await self._retry_policy.wait(attempt)
                else:
                    raise RetryExhaustedError(
                        f"重试 {self.config.max_retries} 次后仍失败",
                        url=url,
                        attempts=attempt,
                        last_error=e
                    ) from e
        
        raise RetryExhaustedError(
            "未知错误",
            url=url,
            attempts=self.config.max_retries,
            last_error=errors[-1] if errors else None
        )
    
    async def _get_once(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        raise_for_status: bool = True
    ) -> str:
        """单次获取（内部方法）"""
        async with self.get_stream(url, headers) as response:
            # 检查内容长度
            content_length = response.content_length
            if content_length and content_length > self.config.max_content_length:
                raise ContentTooLargeError(
                    f"内容过大: {content_length} 字节",
                    url=url,
                    content_length=content_length,
                    max_length=self.config.max_content_length
                )
            
            # 检查状态码
            if raise_for_status and response.status >= 400:
                if response.status == 429:
                    retry_after = response.headers.get("Retry-After")
                    raise RateLimitError(
                        "请求过于频繁",
                        url=url,
                        retry_after=int(retry_after) if retry_after else None
                    )
                raise NetworkError(
                    f"HTTP {response.status}",
                    url=url,
                    status_code=response.status
                )
            
            # 读取内容（限制大小）
            chunks = []
            total_size = 0
            
            async for chunk in response.content.iter_chunked(8192):
                total_size += len(chunk)
                if total_size > self.config.max_content_length:
                    raise ContentTooLargeError(
                        f"内容超过限制: {total_size} 字节",
                        url=url,
                        content_length=total_size,
                        max_length=self.config.max_content_length
                    )
                chunks.append(chunk)
            
            return b"".join(chunks).decode("utf-8", errors="ignore")
