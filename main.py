import uvicorn

from app.http.chat import app  # pyright: ignore[reportUnusedImport]
from core.config import config


def main():
    """启动应用"""
    uvicorn.run(
        "app.http.chat:app",
        host="0.0.0.0",
        port=config.app.port,
        reload=True,
    )


if __name__ == "__main__":
    main()
