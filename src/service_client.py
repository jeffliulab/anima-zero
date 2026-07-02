"""RemoteService：把一个「挂载服务」（world 声明的纯计算顾问，如象棋引擎）接成大脑可调的工具端点。

【service 与 world 的界定（勿混，这是设计约定）】
- **world = ANIMA 栖身的现实**：有画面（perceive）、动作有副作用（过安全闸）、慢动作走
  run_alive 生命迹象监督（见 world_client.py）。交互以**发命令**为主。
- **service = ANIMA 请教的顾问**：无画面、**无副作用是定义**（会改外部状态的东西应做成 world）、
  快问快答走 run_sync 固定短超时。交互是**问答拿反馈**（如给 FEN 回最佳着法）。

因此本客户端只有 capabilities()（tools/list，一次即缓存）+ invoke()（tools/call，短死线），
没有 perceive；工具 kind 一律记 "read"（顾问=只读，不过安全闸）。
每次调用记账 kind="service_call"（awi_log 转发进 session_log，Session Logs 里全链可见）。

挂载来源：world 能力自述里的 services 声明（见 awi.Capabilities.services / registry.services_for）。
信任模型：大脑按 world 声明的 URL 连接 service——本项目全部本机自有进程，接受该信任；
将来接第三方 world 前需加白名单（登记在案的"先别做"）。
"""
from __future__ import annotations

import time
from typing import Any

import httpx

from . import awi_log, config
from .awi import ActionResult, Capabilities, ToolSpec
from .mcp_bridge import run_sync, with_session

PROBE_TIMEOUT = config.WORLD_PROBE_TIMEOUT   # 探在线的短超时（与 world 同款语义）


class RemoteService:
    def __init__(self, name: str, base_url: str, timeout: float = config.SERVICE_MCP_TIMEOUT) -> None:
        self.name = name
        self.base = base_url.rstrip("/")
        self.mcp_url = self.base + "/mcp"
        self.timeout = timeout
        self._caps: Capabilities | None = None   # 能力缓存：握手一次，之后复用

    # ---------- 能力握手（一次 + 缓存）----------
    def capabilities(self) -> Capabilities:
        if self._caps is not None:
            return self._caps

        async def op(s):
            tl = await s.list_tools()
            # 顾问=只读是定义：不管 server 侧 annotations 怎么标，这里一律归 "read"（不过安全闸）。
            return [ToolSpec(name=t.name, description=t.description or "",
                             parameters=t.inputSchema or {"type": "object", "properties": {}},
                             kind="read")
                    for t in tl.tools]

        t0 = time.perf_counter()
        tools = run_sync(with_session(self.mcp_url, op, self.timeout),
                         self.timeout + config.BRIDGE_GRACE_S)
        self._caps = Capabilities(name=self.name, version="", tools=tools)
        awi_log.record(self.name, "capabilities", "capabilities() 握手[mcp·service]",
                       (time.perf_counter() - t0) * 1000,
                       resp={"transport": "mcp", "n_tools": len(tools),
                             "tools": [t.name for t in tools]},
                       kind="service_call")
        return self._caps

    def refresh(self) -> None:
        """丢掉能力缓存，下次 capabilities() 重新握手（服务重启/换了工具后用）。"""
        self._caps = None

    # ---------- 问答（快问快答，固定短死线）----------
    def invoke(self, name: str, **kwargs: Any) -> ActionResult:
        async def op(s):
            r = await s.call_tool(name, kwargs)
            text = "".join(c.text for c in r.content if getattr(c, "text", None))
            data = r.structuredContent or {}
            ok = not bool(getattr(r, "isError", False))
            return ok, text, data

        t0 = time.perf_counter()
        try:
            ok, text, data = run_sync(with_session(self.mcp_url, op, self.timeout),
                                      self.timeout + config.BRIDGE_GRACE_S)
            res = ActionResult(ok=ok, message=text, data=data)
        except Exception as e:
            # 服务没起/超时 → 可读失败原话给大脑（如实反馈，不兜底）。
            res = ActionResult(False, f"服务「{self.name}」调用失败（{type(e).__name__}）——它可能没有启动。")
        awi_log.record(self.name, "invoke", f"{name}({kwargs})", (time.perf_counter() - t0) * 1000,
                       resp={"ok": res.ok, "message": res.message, "has_data": bool(res.data)},
                       kind="service_call")
        return res

    # ---------- 带外探活（/awi 仪表盘用，不记流量）----------
    def online(self) -> bool:
        """能连上它的端口就算在线（FastMCP 纯 MCP 服务没有 /health，404 应答也算活着；连接失败=离线）。"""
        try:
            httpx.get(self.base + "/health", timeout=PROBE_TIMEOUT)
            return True
        except Exception:
            return False
