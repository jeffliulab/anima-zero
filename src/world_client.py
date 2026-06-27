"""RemoteWorld:把一个「独立运行的世界」(sim-desk / 以后 MuJoCo / 真机)接成 anima 的 World。

它实现 World 协议(就是 AWI 的客户端),内部按 URL 调世界的 HTTP 接口(capabilities / perceive / invoke)。
能力(capabilities)在第一次连接时**握手一次并缓存**,之后不再问世界;perceive / invoke 每次记一笔 AWI 流量
(给 /awi 仪表盘看)。所以注册表、编排器一行都不用改——「世界」只是从进程内的 Python 对象,换成了远程世界的瘦客户端。
"""
from __future__ import annotations

import base64
import time
from typing import Any

import httpx

from . import awi_log
from .awi import ActionResult, Capabilities, Observation, ToolSpec

DEFAULT_TIMEOUT = 30.0  # 正常调用世界(capabilities / perceive / invoke)的超时(秒)
ONLINE_PROBE_TIMEOUT = 1.5  # 探「世界在不在线」的短超时(秒);只为快速反馈,不必等满


class RemoteWorld:  # 实现 World 协议(AWI 客户端)
    def __init__(self, name: str, base_url: str, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.name = name
        self.base = base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout)
        self._caps: Capabilities | None = None    # 能力缓存:握手一次,之后复用(见 capabilities)
        self._last_state: dict | None = None       # 最近一次 perceive 的 state(给 /awi 仪表盘看,免得它再 perceive)

    def capabilities(self) -> Capabilities:
        # 握手:第一次拿到就缓存,之后直接返回缓存——不再发 HTTP、不再记流量。
        # 工具清单基本不变;世界换了工具 / 重启,用 refresh() 或重启 ANIMA 来重新握手。
        if self._caps is not None:
            return self._caps
        t0 = time.perf_counter()
        r = self._client.get(self.base + "/capabilities").json()
        tools = [
            ToolSpec(t["name"], t["description"], t["parameters"], t.get("kind", "tool"))
            for t in r.get("tools", [])
        ]
        awi_log.record(self.name, "capabilities", f"→ {len(tools)} 个能力(握手)", (time.perf_counter() - t0) * 1000)
        self._caps = Capabilities(name=r["name"], version=r.get("version", ""), tools=tools)
        return self._caps

    def refresh(self) -> None:
        """丢掉能力缓存,下次 capabilities() 重新握手(世界换了工具 / 重启后用)。"""
        self._caps = None

    def perceive(self) -> Observation:
        t0 = time.perf_counter()
        r = self._client.get(self.base + "/perceive").json()
        img = base64.b64decode(r["image_b64"]) if r.get("image_b64") else None
        state = r.get("state", {})
        awi_log.record(self.name, "perceive", f"→ state={state}", (time.perf_counter() - t0) * 1000)
        self._last_state = state    # 顺手记住,给仪表盘显示(免得仪表盘为了看状态又 perceive 一次)
        return Observation(image_png=img, state=state)

    def last_state(self) -> dict | None:
        """最近一次 perceive 到的 state(没感知过则 None)。给 /awi 仪表盘读,免得它再 perceive。"""
        return self._last_state

    def invoke(self, name: str, **kwargs: Any) -> ActionResult:
        t0 = time.perf_counter()
        r = self._client.post(self.base + "/invoke", json={"name": name, "args": kwargs}).json()
        awi_log.record(self.name, "invoke", f"{name}({kwargs}) → {r.get('message', '')}", (time.perf_counter() - t0) * 1000)
        return ActionResult(ok=r.get("ok", False), message=r.get("message", ""), data=r.get("data", {}))

    def online(self) -> bool:
        """世界在不在线(给 /api/worlds、/api/awi 用),短超时探一下。
        探的是世界专门的 /health 端点(世界不记它的流量),所以不会刷世界终端的 AWI 日志。"""
        try:
            self._client.get(self.base + "/health", timeout=ONLINE_PROBE_TIMEOUT)
            return True
        except Exception:
            return False
