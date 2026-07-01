"""RemoteWorld：把一个「独立运行的世界」接成 anima 的 World（AWI 客户端）。

**接口采标 MCP（v0.4）**：世界现在是标准 **MCP server**——大脑经官方 MCP SDK 连它的 `/mcp` 端点：
  - `capabilities()` ← MCP `tools/list`（动作）+ `prompts/get "guidance"`（说明书）
  - `perceive()`    ← MCP `resources/read anima://observation`（快照图 + 结构 state）
  - `invoke()`      ← MCP `tools/call`
MCP 是 async 的，经 `mcp_bridge` 同步桥调用（见该文件）。能力握手一次即缓存。

**过渡期双路**：迁移是逐个世界做的，所以首次握手先试 MCP，连不上（世界还没改成 MCP server）就**回退旧 HTTP
AWI**（GET /capabilities、GET /perceive、POST /invoke）。等四个世界全迁完，删掉旧分支即可。

**永远带外**：`/health`（探活）、`/status`（上帝视角真值，绝不进 perceive）、`/stream`（MJPEG 直播）始终走普通
HTTP，不进 MCP——这是红线（MCP 只跑 JSON-RPC 文本，传不了视频流）。
"""
from __future__ import annotations

import base64
import json
import time
from typing import Any

import httpx
from pydantic import AnyUrl

from . import awi_log, config
from .awi import ActionResult, Capabilities, Observation, ToolSpec
from .mcp_bridge import run_sync, with_session

DEFAULT_TIMEOUT = config.WORLD_TIMEOUT       # 正常调用世界的超时（config，env 可覆盖）
ONLINE_PROBE_TIMEOUT = config.WORLD_PROBE_TIMEOUT  # 探在线的短超时

# MCP 契约常量（世界侧适配器 awi_mcp.py 用同样的字符串，两边必须一致）。
OBSERVATION_URI = "anima://observation"   # 感知资源：读它拿到 state(text) + 画面(image/png blob)
GUIDANCE_PROMPT = "guidance"              # 说明书提示词名


class RemoteWorld:  # 实现 World 协议(AWI 客户端)
    def __init__(self, name: str, base_url: str, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.name = name
        self.base = base_url.rstrip("/")
        self.mcp_url = self.base + "/mcp"
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)  # 带外用(/health /status /stream) + 旧 HTTP 回退
        self._caps: Capabilities | None = None    # 能力缓存:握手一次,之后复用
        self._transport: str | None = None        # None=未探测 / "mcp" / "http"（回退）
        self._last_state: dict | None = None       # 最近一次 perceive 的 state(给 /awi 仪表盘看)

    # ---------- 能力握手（探测传输方式 + 缓存）----------
    def capabilities(self) -> Capabilities:
        if self._caps is not None:
            return self._caps
        t0 = time.perf_counter()
        caps = self._caps_mcp()          # 先试 MCP
        if caps is None:
            caps = self._caps_http()     # 回退旧 HTTP AWI
        self._caps = caps
        awi_log.record(self.name, "capabilities", f"capabilities() 握手[{self._transport}]",
                       (time.perf_counter() - t0) * 1000,
                       resp={"transport": self._transport, "n_tools": len(caps.tools),
                             "tools": [t.name for t in caps.tools], "has_guidance": bool(caps.guidance)})
        return caps

    def _caps_mcp(self) -> Capabilities | None:
        async def op(s):
            tl = await s.list_tools()
            tools = [ToolSpec(
                        name=t.name, description=t.description or "",
                        parameters=t.inputSchema or {"type": "object", "properties": {}},
                        # MCP 无 anima 的 kind 概念：readOnlyHint=真 → 非改世界（read/judge 归一为 "read"）。
                        kind="read" if (t.annotations and t.annotations.readOnlyHint) else "tool")
                     for t in tl.tools]
            guidance = ""
            try:
                pl = await s.list_prompts()
                if any(p.name == GUIDANCE_PROMPT for p in pl.prompts):
                    gp = await s.get_prompt(GUIDANCE_PROMPT, {})
                    guidance = "".join(m.content.text for m in gp.messages
                                       if getattr(m.content, "text", None))
            except Exception:
                pass
            return tools, guidance
        try:
            tools, guidance = run_sync(with_session(self.mcp_url, op, self.timeout), self.timeout + 5)
        except Exception:
            return None
        self._transport = "mcp"
        return Capabilities(name=self.name, version="", tools=tools, state_schema={}, guidance=guidance)

    def _caps_http(self) -> Capabilities:
        r = self._client.get(self.base + "/capabilities").json()
        tools = [ToolSpec(t["name"], t["description"], t["parameters"], t.get("kind", "tool"))
                 for t in r.get("tools", [])]
        self._transport = "http"
        return Capabilities(name=r["name"], version=r.get("version", ""), tools=tools,
                            state_schema=r.get("state_schema", {}) or {}, guidance=r.get("guidance", "") or "")

    def refresh(self) -> None:
        """丢掉能力缓存,下次 capabilities() 重新握手(世界换了工具 / 重启后用)。"""
        self._caps = None
        self._transport = None

    # ---------- 感知 ----------
    def perceive(self) -> Observation:
        if self._transport is None:
            self.capabilities()  # 确保已探测传输方式
        t0 = time.perf_counter()
        obs = self._perceive_mcp() if self._transport == "mcp" else self._perceive_http()
        awi_log.record(self.name, "perceive", "perceive()", (time.perf_counter() - t0) * 1000,
                       resp={"img_bytes": len(obs.image_png) if obs.image_png else 0, "state": obs.state})
        self._last_state = obs.state
        return obs

    def _perceive_mcp(self) -> Observation:
        async def op(s):
            rd = await s.read_resource(AnyUrl(OBSERVATION_URI))
            state: dict = {}
            img: bytes | None = None
            for c in rd.contents:
                if getattr(c, "text", None) is not None:
                    try:
                        state = json.loads(c.text) or {}
                    except Exception:
                        state = {}
                elif getattr(c, "blob", None) is not None:
                    img = base64.b64decode(c.blob)
            return state, img
        try:
            state, img = run_sync(with_session(self.mcp_url, op, self.timeout), self.timeout + 5)
        except Exception:
            state, img = {}, None
        return Observation(image_png=img, state=state)

    def _perceive_http(self) -> Observation:
        r = self._client.get(self.base + "/perceive").json()
        img = base64.b64decode(r["image_b64"]) if r.get("image_b64") else None
        return Observation(image_png=img, state=r.get("state", {}))

    def last_state(self) -> dict | None:
        """最近一次 perceive 到的 state(没感知过则 None)。给 /awi 仪表盘读。"""
        return self._last_state

    # ---------- 动作 ----------
    def invoke(self, name: str, **kwargs: Any) -> ActionResult:
        if self._transport is None:
            self.capabilities()
        t0 = time.perf_counter()
        res = self._invoke_mcp(name, kwargs) if self._transport == "mcp" else self._invoke_http(name, kwargs)
        awi_log.record(self.name, "invoke", f"{name}({kwargs})", (time.perf_counter() - t0) * 1000,
                       resp={"ok": res.ok, "message": res.message, "has_data": bool(res.data)})
        return res

    def _invoke_mcp(self, name: str, args: dict) -> ActionResult:
        async def op(s):
            r = await s.call_tool(name, args)
            text = "".join(c.text for c in r.content if getattr(c, "text", None))
            data = r.structuredContent or {}
            ok = not bool(getattr(r, "isError", False))
            return ok, text, data
        try:
            ok, text, data = run_sync(with_session(self.mcp_url, op, self.timeout), self.timeout + 5)
        except Exception as e:
            return ActionResult(False, f"（世界调用失败：{type(e).__name__}）")
        return ActionResult(ok=ok, message=text, data=data)

    def _invoke_http(self, name: str, args: dict) -> ActionResult:
        r = self._client.post(self.base + "/invoke", json={"name": name, "args": args}).json()
        return ActionResult(ok=r.get("ok", False), message=r.get("message", ""), data=r.get("data", {}))

    # ---------- 带外（探活 / 上帝视角真值 / 直播）：始终普通 HTTP，与传输方式无关 ----------
    def debug_state(self) -> dict | None:
        """【人类调试台专用·世界真值】走世界本地 `/status`（非 AWI 通道，绝不给 ANIMA）。没有 /status → None。"""
        try:
            r = self._client.get(self.base + "/status", timeout=config.WORLD_STATUS_TIMEOUT)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return None

    def online(self) -> bool:
        """探活（/api/worlds、/api/awi 用），短超时探世界的 /health（不记流量）。"""
        try:
            self._client.get(self.base + "/health", timeout=ONLINE_PROBE_TIMEOUT)
            return True
        except Exception:
            return False

    def close(self) -> None:
        """关掉底层 httpx 连接（对弈 loop 退出时清理它自己那个短超时 client 用；共享世界 client 别关）。"""
        try:
            self._client.close()
        except Exception:
            pass
