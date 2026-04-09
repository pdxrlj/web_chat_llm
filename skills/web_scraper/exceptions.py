"""Web Scraper 自定义异常"""

from typing import Optional


class ScraperException(Exception):
    """Scraper 基础异常"""
    
    def __init__(self, message: str, url: Optional[str] = None):
        self.message = message
        self.url = url
        super().__init__(self.message)
    
    def __str__(self) -> str:
        if self.url:
            return f"{self.message} (URL: {self.url})"
        return self.message


class URLValidationError(ScraperException):
    """URL 验证失败"""
    pass


class NetworkError(ScraperException):
    """网络错误"""
    
    def __init__(
        self,
        message: str,
        url: Optional[str] = None,
        status_code: Optional[int] = None
    ):
        self.status_code = status_code
        super().__init__(message, url)
    
    def __str__(self) -> str:
        base = super().__str__()
        if self.status_code:
            return f"{base} (Status: {self.status_code})"
        return base


class TimeoutError(ScraperException):
    """请求超时"""
    pass


class RateLimitError(ScraperException):
    """速率限制错误"""
    
    def __init__(
        self,
        message: str = "请求过于频繁",
        url: Optional[str] = None,
        retry_after: Optional[int] = None
    ):
        self.retry_after = retry_after
        super().__init__(message, url)


class ContentTooLargeError(ScraperException):
    """内容过大"""
    
    def __init__(
        self,
        message: str,
        url: Optional[str] = None,
        content_length: Optional[int] = None,
        max_length: Optional[int] = None
    ):
        self.content_length = content_length
        self.max_length = max_length
        super().__init__(message, url)
    
    def __str__(self) -> str:
        base = super().__str__()
        if self.content_length and self.max_length:
            return f"{base} (Size: {self.content_length}, Max: {self.max_length})"
        return base


class RetryExhaustedError(ScraperException):
    """重试次数耗尽"""
    
    def __init__(
        self,
        message: str,
        url: Optional[str] = None,
        attempts: int = 0,
        last_error: Optional[Exception] = None
    ):
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(message, url)
    
    def __str__(self) -> str:
        base = super().__str__()
        return f"{base} (Attempts: {self.attempts}, Last Error: {self.last_error})"


class ParseError(ScraperException):
    """内容解析失败"""
    pass
