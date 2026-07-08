"""同步 ↔ 异步桥 + 世界调用的「生命迹象」监督。

MCP 官方 SDK 是 async 的，而 ANIMA 的 orchestrator 是同步循环——这里跑一个**常驻后台事件循环**
（守护线程），同步代码用 `run_sync()` / `run_alive()` 把协程丢进去、阻塞等结果。
`with_session()` 对一个 MCP 端点（world / engine）**短连一次 → 做一件事 → 断开**：服务端跑 stateless
streamable-HTTP，每次请求独立；能力清单在上层（RemoteWorld）已缓存，所以每 tick 只是一次读感知/发动作，
短连开销可接受（认知决策速率，非硬实时；这正是 MCP 适配机器人的方式——慢层走 MCP，快层留 ROS/CAN）。

**run_alive（v0.5 wave 0）**：物理世界的一个动作可能要几十秒。MCP 规范对长任务的指导是
「收到 progress notification 应重置超时（SHOULD），另设总上限」——SDK 1.28.1 不实现这条 SHOULD
（其 read timeout 是固定死线），由这里落地：**收到进度就续命，X 秒无生命迹象才判失联，
另有总上限硬闸 + 上层随时取消**。别把 run_alive 换回固定死线——那正是 v0.4 move 假死 35s 的根因。
"""
from __future__ import annotations

import asyncio
import threading
import time
from typing import Awaitable, Callable, Optional, TypeVar

import httpx
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from .. import config

_T = TypeVar("_T")

_loop: asyncio.AbstractEventLoop | None = None
_lock = threading.Lock()


class WorldCallError(Exception):
    """世界调用的类型化失败基类（给上层区分「为什么没等到」用）。"""


class LivenessTimeout(WorldCallError):
    """失联：连续 X 秒没有任何生命迹象（没结果、也没进度）。"""


class HardCapTimeout(WorldCallError):
    """超总上限：一直有生命迹象，但整个动作超过了单次上限，放弃等待。"""


class CallAborted(WorldCallError):
    """上层要求放弃等待（用户取消 / 换局 / 令牌失效）。注意：放弃等待 ≠ 世界停手。"""


class Beat:
    """心跳：progress 回调里 touch() 一下 = 「世界还活着」，liveness 倒计时随之重置。"""

    def __init__(self) -> None:
        self._last = time.monotonic()

    def touch(self) -> None:
        self._last = time.monotonic()

    def age(self) -> float:
        return time.monotonic() - self._last


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
    """同步阻塞地跑一个协程到完成，固定死线，超时抛 TimeoutError。只用于【快速读操作】。"""
    fut = asyncio.run_coroutine_threadsafe(coro, _ensure_loop())
    return fut.result(timeout=timeout)


def run_alive(coro: Awaitable[_T], *, beat: Beat, liveness_s: float, hard_cap_s: float,
              should_abort: Optional[Callable[[], bool]] = None) -> _T:
    """同步阻塞地跑一个协程，按「生命迹象」语义监督（用于可能很慢的动作调用）。

    - beat：心跳（调用方把 progress 回调接到 beat.touch()）；
    - liveness_s：连续这么多秒没有心跳 → 取消任务、抛 LivenessTimeout；
    - hard_cap_s：总时长上限 → 取消任务、抛 HardCapTimeout（有心跳也不无限等）；
    - should_abort：每个巡检步长问一次，返回 True → 取消任务、抛 CallAborted（取消响应粒度
      = config.BRIDGE_WATCHDOG_POLL_S）。
    """
    async def _supervise() -> _T:
        task = asyncio.ensure_future(coro)
        start = time.monotonic()
        try:
            while True:
                done, _ = await asyncio.wait({task}, timeout=config.BRIDGE_WATCHDOG_POLL_S)
                if done:
                    return task.result()
                if should_abort is not None and should_abort():
                    raise CallAborted("上层要求放弃等待")
                if beat.age() > liveness_s:
                    raise LivenessTimeout(f"{liveness_s:g}s 无生命迹象")
                if time.monotonic() - start > hard_cap_s:
                    raise HardCapTimeout(f"超过总上限 {hard_cap_s:g}s")
        finally:
            if not task.done():
                task.cancel()

    fut = asyncio.run_coroutine_threadsafe(_supervise(), _ensure_loop())
    # 外层 future 只是后备安全带（监督器才是权威）；宽限量在 config，不是魔法数。
    return fut.result(timeout=hard_cap_s + config.BRIDGE_GRACE_S)


async def with_session(mcp_url: str, op: Callable[[ClientSession], Awaitable[_T]], timeout: float,
                       read_timeout: float | None = None) -> _T:
    """短连一个 MCP 端点、initialize 握手、跑一次 op(session)、断开。

    timeout = 连接/写/池的死线；read_timeout = 流上两次数据之间的最大间隔（长动作给 liveness
    级别的余量——progress 也是数据，会重置它），不传则同 timeout。
    """
    t = httpx.Timeout(timeout, read=read_timeout if read_timeout is not None else timeout)
    async with httpx.AsyncClient(timeout=t, follow_redirects=True) as hc:
        async with streamable_http_client(mcp_url, http_client=hc) as (reader, writer, _):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                return await op(session)
