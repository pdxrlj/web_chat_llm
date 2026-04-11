#!/usr/bin/env python3
"""
Web 页面抓取脚本

使用方式：
    uv run skills/web-scraper/scraper_script.py fetch "https://www.baidu.com"
    uv run skills/web-scraper/scraper_script.py text "https://www.baidu.com"
    uv run skills/web-scraper/scraper_script.py links "https://www.baidu.com"
"""

import asyncio
import importlib.util
import sys
import os

# Windows 控制台默认 GBK，设置 UTF-8 输出避免 emoji 编码错误
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

# 用 importlib 将 web-scraper 目录作为包正确加载（支持相对导入）
_pkg_dir = os.path.dirname(os.path.abspath(__file__))
_init_path = os.path.join(_pkg_dir, "__init__.py")
_spec = importlib.util.spec_from_file_location(
    "web_scraper", _init_path, submodule_search_locations=[_pkg_dir]
)
assert _spec is not None and _spec.loader is not None, f"无法加载包: {_init_path}"
_pkg = importlib.util.module_from_spec(_spec)
sys.modules["web_scraper"] = _pkg
_spec.loader.exec_module(_pkg)

fetch_webpage = _pkg.fetch_webpage
extract_text = _pkg.extract_text
extract_links = _pkg.extract_links
close_client = _pkg.close_client


def main():
    if len(sys.argv) < 3:
        print("使用方式: uv run skills/web-scraper/scraper_script.py <command> <url>")
        print("命令:")
        print("  fetch  - 抓取网页（返回基本信息+前500字符）")
        print("  text   - 抓取网页并提取纯文本")
        print("  links  - 抓取网页并提取链接")
        print("示例:")
        print(
            "  uv run skills/web-scraper/scraper_script.py fetch 'https://www.baidu.com'"
        )
        print(
            "  uv run skills/web-scraper/scraper_script.py text 'https://www.baidu.com'"
        )
        sys.exit(1)

    command = sys.argv[1].strip().lower()
    url = sys.argv[2].strip()

    # 自动补全 https://
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    try:
        html = asyncio.run(fetch_webpage(url))

        if command == "fetch":
            print(html)
        elif command == "text":
            print(extract_text(html))
        elif command == "links":
            print(extract_links(html, url))
        else:
            print(f"未知命令: {command}")
            print("支持: fetch, text, links")
            sys.exit(1)
    except Exception as e:
        print(f"错误: {e}")
        sys.exit(1)
    finally:
        asyncio.run(close_client())


if __name__ == "__main__":
    main()
