"""工具函数"""

import re
from urllib.parse import urlparse
from typing import Optional, List, Dict

from .exceptions import URLValidationError


def validate_url(url: str) -> str:
    """验证 URL 格式
    
    Args:
        url: 待验证的 URL
    
    Returns:
        验证通过的 URL
    
    Raises:
        URLValidationError: URL 格式不正确
    """
    if not url or not isinstance(url, str):
        raise URLValidationError("URL 不能为空")
    
    url = url.strip()
    
    # 自动添加 https://
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    
    try:
        parsed = urlparse(url)
        
        if not parsed.scheme:
            raise URLValidationError("缺少协议（http/https）", url=url)
        
        if not parsed.netloc:
            raise URLValidationError("缺少域名", url=url)
        
        # 检查域名格式
        domain_pattern = r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z]{2,})+$"
        if not re.match(domain_pattern, parsed.netloc.split(":")[0]):
            raise URLValidationError("域名格式不正确", url=url)
        
        return url
    
    except Exception as e:
        raise URLValidationError(f"URL 解析失败: {str(e)}", url=url) from e


def extract_text_from_html(
    html: str,
    max_length: int = 10000,
    remove_scripts: bool = True,
    remove_styles: bool = True,
    remove_comments: bool = True
) -> str:
    """从 HTML 提取纯文本
    
    Args:
        html: HTML 内容
        max_length: 最大文本长度
        remove_scripts: 是否移除脚本
        remove_styles: 是否移除样式
        remove_comments: 是否移除注释
    
    Returns:
        提取的纯文本
    """
    try:
        from bs4 import BeautifulSoup, Comment
    except ImportError:
        raise ImportError(
            "需要安装 beautifulsoup4\n"
            "运行: pip install beautifulsoup4"
        )
    
    soup = BeautifulSoup(html, "html.parser")
    
    # 移除不需要的元素
    if remove_scripts:
        for script in soup.find_all("script"):
            script.decompose()
    
    if remove_styles:
        for style in soup.find_all("style"):
            style.decompose()
    
    if remove_comments:
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()
    
    # 移除隐藏元素
    for hidden in soup.find_all(style=re.compile(r"display:\s*none")):
        hidden.decompose()
    
    # 提取文本
    text = soup.get_text(separator="\n")
    
    # 清理空白
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = "\n".join(chunk for chunk in chunks if chunk)
    
    # 限制长度
    if len(text) > max_length:
        text = text[:max_length] + f"\n\n... (已截断，总长度: {len(text)} 字符)"
    
    return text


def extract_links_from_html(html: str, base_url: Optional[str] = None) -> List[Dict[str, str]]:
    """从 HTML 提取链接
    
    Args:
        html: HTML 内容
        base_url: 基础 URL（用于解析相对链接）
    
    Returns:
        链接列表，每个链接包含 text 和 url
    """
    try:
        from bs4 import BeautifulSoup
        from urllib.parse import urljoin
    except ImportError:
        return []
    
    soup = BeautifulSoup(html, "html.parser")
    links = []
    
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(strip=True)
        
        # 跳过空链接、锚点、JavaScript
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        
        # 解析相对链接
        if base_url:
            href = urljoin(base_url, href)
        
        links.append({
            "text": text or href,
            "url": href
        })
    
    return links


def extract_metadata_from_html(html: str) -> Dict[str, str]:
    """从 HTML 提取元数据
    
    Args:
        html: HTML 内容
    
    Returns:
        元数据字典（title, description, keywords 等）
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return {}
    
    soup = BeautifulSoup(html, "html.parser")
    metadata = {}
    
    # 提取标题
    if title := soup.find("title"):
        metadata["title"] = title.get_text(strip=True)
    
    # 提取 meta 标签
    for meta in soup.find_all("meta"):
        name = meta.get("name") or meta.get("property")
        content = meta.get("content")
        
        if name and content:
            metadata[name] = content
    
    return metadata


def is_content_type_allowed(content_type: Optional[str]) -> bool:
    """检查内容类型是否允许
    
    Args:
        content_type: 内容类型
    
    Returns:
        是否允许
    """
    if not content_type:
        return True
    
    # 允许的类型
    allowed_types = [
        "text/html",
        "text/plain",
        "application/xhtml+xml",
        "application/xml"
    ]
    
    # 检查是否匹配
    content_type_lower = content_type.lower()
    return any(allowed in content_type_lower for allowed in allowed_types)
