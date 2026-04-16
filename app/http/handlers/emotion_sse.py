from app.http.handlers.base import router
from fastapi import Request
from fastapi.responses import StreamingResponse
from app.http.response import NlResponse
from core.nl_chat.middlewares.common import message_bus
import asyncio
import logging
from typing import Dict, Set, AsyncGenerator
import json

# 配置日志
logger = logging.getLogger(__name__)


class SSEConnectionManager:
    """SSE连接管理器，用于根据session_id分发消息"""

    def __init__(self):
        # 存储session_id到连接队列的映射
        # key: session_id, value: Set[asyncio.Queue]
        self._connections: Dict[str, Set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def add_connection(self, session_id: str) -> asyncio.Queue:
        """添加新的连接"""
        queue = asyncio.Queue(maxsize=100)  # 设置队列最大长度

        async with self._lock:
            if session_id not in self._connections:
                self._connections[session_id] = set()
            self._connections[session_id].add(queue)
            logger.info(
                f"SSE连接已添加 - session_id: {session_id}, 当前连接数: {len(self._connections[session_id])}"
            )

        return queue

    async def remove_connection(self, session_id: str, queue: asyncio.Queue) -> None:
        """移除连接"""
        async with self._lock:
            if session_id in self._connections:
                self._connections[session_id].discard(queue)
                logger.info(
                    f"SSE连接已移除 - session_id: {session_id}, 当前连接数: {len(self._connections[session_id])}"
                )

                # 如果该session_id没有连接了，清理掉
                if not self._connections[session_id]:
                    del self._connections[session_id]
                    logger.info(f"已清理session_id: {session_id}的所有连接")

    async def send_message(self, session_id: str, message: Dict) -> None:
        """发送消息给指定session_id的所有连接"""
        async with self._lock:
            if session_id not in self._connections:
                logger.debug(f"没有找到session_id: {session_id}的连接")
                return

            # 序列化消息
            json_message = json.dumps(message, ensure_ascii=False)
            sse_message = f"data: {json_message}\n\n"

            # 发送给该session_id的所有连接
            queues = list(self._connections[session_id])

        for queue in queues:
            try:
                # 使用put_nowait避免阻塞
                queue.put_nowait(sse_message)
            except asyncio.QueueFull:
                logger.warning(f"session_id: {session_id}的连接队列已满，消息将被丢弃")


# 创建全局连接管理器
connection_manager = SSEConnectionManager()


# 单独的消息处理函数，用于处理message_bus的消息
@message_bus.connect
def handle_message_bus(sender, **kwargs):
    """处理从message_bus接收到的消息"""
    message = kwargs.get("message", {})
    logger.info(f"从message_bus接收消息 - 发送者: {sender}, 消息: {message}")

    # 获取消息中的session_id
    session_id = message.get("session_id")
    if not session_id:
        logger.warning("消息中没有session_id，无法分发")
        return

    # 将消息发送给对应的连接
    # 注意：这里使用asyncio.create_task来避免阻塞信号处理
    asyncio.create_task(connection_manager.send_message(session_id, message))


@router.get("/chat/user/message/sse")
async def sse_handler(request: Request):
    """SSE端点，用于实时推送情感分析结果"""
    # 1. 读取header中的session_id
    session_id = request.headers.get("session_id")
    if not session_id:
        return NlResponse(
            content={},
            message="session_id is required in header",
            status_code=400,
        )

    # 2. 添加连接到管理器
    message_queue = await connection_manager.add_connection(session_id)

    async def event_generator() -> AsyncGenerator[str, None]:
        """事件生成器，持续发送消息给客户端"""
        try:
            # 发送连接成功的初始事件
            initial_message = {
                "event": "connected",
                "message": "SSE连接已建立",
                "session_id": session_id,
            }
            yield f"data: {json.dumps(initial_message, ensure_ascii=False)}\n\n"

            while True:
                # 检查客户端是否断开连接
                if await request.is_disconnected():
                    logger.info(f"客户端已断开连接 - session_id: {session_id}")
                    break

                try:
                    # 等待消息（带超时的非阻塞等待）
                    message = await asyncio.wait_for(message_queue.get(), timeout=1.0)
                    yield message
                    message_queue.task_done()
                except asyncio.TimeoutError:
                    # 不发送心跳消息，直接继续循环
                    continue
                except asyncio.CancelledError:
                    logger.info(f"SSE连接已取消 - session_id: {session_id}")
                    break
        finally:
            # 清理连接
            await connection_manager.remove_connection(session_id, message_queue)

    # 3. 返回StreamingResponse
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用代理缓冲
        },
    )
