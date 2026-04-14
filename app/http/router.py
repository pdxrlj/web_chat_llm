from collections.abc import Sequence
from contextlib import asynccontextmanager
import importlib
from pathlib import Path
import pkgutil
from typing import cast

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.http.response import NlResponse
from core.config import PostgresStorageConfig
from core.logger import setup_logger
from core.model.base import close, conn, migrate

logger = setup_logger("lifespan")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """
    应用生命周期管理。

    启动时：
        - 加载配置
        - 初始化数据库连接
        - 执行数据库迁移

    关闭时：
        - 关闭数据库连接池
    """
    # 启动阶段
    logger.info("Application startup")

    # 加载配置
    from core.config import config

    # 初始化数据库连接
    postgres_config = config.get_storage("postgres")
    if postgres_config and isinstance(postgres_config, PostgresStorageConfig):
        conn_str = (
            f"postgresql+asyncpg://{postgres_config.user}:{postgres_config.password}"
            f"@{postgres_config.host}:{postgres_config.port}/{postgres_config.db_name}"
        )
        conn(conn_str)
        logger.info(
            f"数据库连接已初始化: {postgres_config.host}:{postgres_config.port}"
        )

        # 执行数据库迁移
        await migrate()
        logger.info("数据库迁移完成")
    else:
        logger.warning("未找到 PostgreSQL 配置，跳过数据库初始化")

    yield

    # 关闭阶段
    logger.info("Application shutdown")
    await close()
    logger.info("数据库连接已关闭")


def register_handlers(app: FastAPI) -> None:
    """注册处理器"""

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(  # pyright: ignore[reportUnusedFunction]
        _request: Request, exc: RequestValidationError
    ):
        errors: Sequence[dict[str, object]] = exc.errors()
        first_error: dict[str, object] = errors[0] if errors else {}

        loc_raw = first_error.get("loc", ())
        loc = cast(tuple[object, ...], loc_raw) if isinstance(loc_raw, tuple) else ()
        field = ".".join(str(loc_item) for loc_item in loc[1:]) if len(loc) > 1 else ""

        msg_raw = first_error.get("msg", "参数验证失败")
        msg = str(msg_raw) if msg_raw is not None else "参数验证失败"
        if msg.startswith("Value error, "):
            msg = msg[13:]

        logger.error(f"参数验证失败: {msg}, field: {field}")

        return NlResponse(
            content={},
            message=f"{msg}, field: {field}" if field else msg,
            status_code=400,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(  # pyright: ignore[reportUnusedFunction]
        _request: Request, exc: StarletteHTTPException
    ):
        return NlResponse(content={}, message=exc.detail, status_code=exc.status_code)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def register_routes(app: FastAPI, package_path: str) -> None:
    """自动注册路由"""
    package = importlib.import_module(package_path)
    package_file = package.__file__
    if package_file is None:
        logger.warning(f"无法获取包路径: {package_path}")
        return

    package_dir = str(Path(package_file).parent)
    for _, name, _ in pkgutil.iter_modules([package_dir]):
        if name.startswith("__"):
            continue
        module = importlib.import_module(f"{package_path}.{name}")
        router = getattr(module, "router", None)
        if isinstance(router, APIRouter):
            app.include_router(router)
            logger.info(f"注册路由: {package_path}.{name}")
