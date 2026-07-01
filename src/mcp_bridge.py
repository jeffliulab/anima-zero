"""同步 ↔ 异步桥：MCP 官方 SDK 是 async 的，而 ANIMA 的 orchestrator 是同步循环。

这里跑一个**常驻后台事件循环**（守护线程），同步代码用 `run_sync()` 把协程丢进去、阻塞等结果。
`with_session()` 对一个 MCP 端点（world / engine）**短连一次 → 做一件事 → 断开**：服务端跑 stateless
streamable-HTTP，每次请求独立；能力清单在上层（RemoteWorld）已缓存，所以每 tick 只是一次读感知/发动作，
短连开销可接受（认知决策速率，非硬实时；这正是 MCP 适配机器人的方式——慢层走 MCP，快层留 ROS/CAN）。
"""
from __future__ import annotations

import asyncio
import threading
from typing import Awaitable, Callable, TypeVar

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client

_T = TypeVar("_T")

_loop: asyncio.AbstractEventLoop | None = None
_lock = threading.Lock()


def _ensure_loop() -> asyncio.AbstractEventLoop:
    """懒启动那个常驻后台事件循环（第一次用到时起，之后复用）。"""
    global _loop
    with _lock:
        if _loop is None:
            loop = asyncio.new_event_loop()
            threading.Thread(target=loop.run_forever, name="mcp-bridge-loop", daemon=True).start()
            _loop = loop
        return _loop


def run_sync(coro: Awaitable[_T], timeout: float) -> _T:
    """同步阻塞地跑一个协程到完成，超时抛 TimeoutError。"""
    fut = asyncio.run_coroutine_threadsafe(coro, _ensure_loop())
    return fut.result(timeout=timeout)


async def with_session(mcp_url: str, op: Callable[[ClientSession], Awaitable[_T]], timeout: float) -> _T:
    """短连一个 MCP 端点、initialize 握手、跑一次 op(session)、断开。"""
    async with streamablehttp_client(mcp_url, timeout=timeout) as (reader, writer, _):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            return await op(session)
