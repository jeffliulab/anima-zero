"""RemoteWorld：把一个「独立运行的世界」接成 anima 的 World（AWI 客户端）。

**接口 = 标准 MCP（v0.4 采标，v0.5 收口单路）**：世界是标准 **MCP server**——大脑经官方 MCP SDK
连它的 `/mcp` 端点：
  - `capabilities()` ← MCP `tools/list`（动作）+ `prompts/get "guidance"`（说明书）
  - `perceive()`    ← MCP `resources/read anima://observation`（快照图 + 结构 state）
  - `invoke()`      ← MCP `tools/call`（带 progress：世界报进度=生命迹象，见下）
MCP 是 async 的，经 `mcp_bridge` 同步桥调用（见该文件）。能力握手一次即缓存。
（v0.4 的旧 HTTP AWI 回退双路已删：四个世界全迁 MCP 后它只剩死代码 + transport 粘滞的坑。）

**长动作语义（v0.5 wave 0）**：物理动作可能几十秒。`invoke` 不再掐固定死线，而是「生命迹象」监督
（mcp_bridge.run_alive）：世界经 MCP progress 报进度即续命，X 秒无迹象才判失联，另有总上限硬闸；
进度自动写 AWI 日志（仪表盘可见），还可经 `_on_progress` 转发给调用方（如对弈树发到事件流）。
读操作（capabilities/perceive）本该秒回，仍用 WORLD_TIMEOUT 死线。

**永远带外**：`/health`（探活）、`/status`（上帝视角真值，绝不进 perceive）、`/stream`（MJPEG 直播）
始终走普通 HTTP，不进 MCP——这是红线（MCP 只跑 JSON-RPC 文本，传不了视频流）。
"""
from __future__ import annotations

import base64
import json
import time
from typing import Any, Callable, Optional

import httpx
from pydantic import AnyUrl

from . import awi_log, config, mcp_bridge
from .awi import ActionResult, Capabilities, Observation, ToolSpec
from .mcp_bridge import run_sync, with_session

DEFAULT_TIMEOUT = config.WORLD_TIMEOUT       # 读操作（capabilities/perceive）的死线（config，env 可覆盖）
ONLINE_PROBE_TIMEOUT = config.WORLD_PROBE_TIMEOUT  # 探在线的短超时

# MCP 契约常量（世界侧适配器 awi_mcp.py 用同样的字符串，两边必须一致）。
OBSERVATION_URI = "anima://observation"   # 感知资源：读它拿到 state(text) + 画面(image/png blob)
GUIDANCE_PROMPT = "guidance"              # 说明书提示词名
SERVICES_URI = "anima://services"         # 挂载服务声明资源：JSON 列表 [{"name","url"}]（没声明的世界没有此资源）


class RemoteWorld:  # 实现 World 协议(AWI 客户端)
    def __init__(self, name: str, base_url: str, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.name = name
        self.base = base_url.rstrip("/")
        self.mcp_url = self.base + "/mcp"
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)  # 带外专用(/health /status /stream)
        self._caps: Capabilities | None = None    # 能力缓存:握手一次,之后复用
        self._last_state: dict | None = None       # 最近一次 perceive 的 state(给 /awi 仪表盘看)

    # ---------- 能力握手（一次 + 缓存）----------
    def capabilities(self) -> Capabilities:
        if self._caps is not None:
            return self._caps

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
            services: list[dict] = []
            try:
                rd = await s.read_resource(AnyUrl(SERVICES_URI))
                for c in rd.contents:
                    if getattr(c, "text", None):
                        services = json.loads(c.text) or []
            except Exception:
                pass   # 世界没声明挂载服务（没有该资源）→ 空清单
            return tools, guidance, services

        t0 = time.perf_counter()
        tools, guidance, services = run_sync(with_session(self.mcp_url, op, self.timeout),
                                             self.timeout + config.BRIDGE_GRACE_S)
        self._caps = Capabilities(name=self.name, version="", tools=tools, state_schema={},
                                  guidance=guidance, services=services)
        awi_log.record(self.name, "capabilities", "capabilities() 握手[mcp]",
                       (time.perf_counter() - t0) * 1000,
                       resp={"transport": "mcp", "n_tools": len(tools),
                             "tools": [t.name for t in tools], "has_guidance": bool(guidance),
                             "services": [s.get("name", "") for s in services]})
        return self._caps

    def refresh(self) -> None:
        """丢掉能力缓存,下次 capabilities() 重新握手(世界换了工具 / 重启后用)。"""
        self._caps = None

    # ---------- 感知（快速读，固定死线）----------
    def perceive(self) -> Observation:
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

        t0 = time.perf_counter()
        try:
            state, img = run_sync(with_session(self.mcp_url, op, self.timeout),
                                  self.timeout + config.BRIDGE_GRACE_S)
        except Exception:
            state, img = {}, None
        obs = Observation(image_png=img, state=state)
        awi_log.record(self.name, "perceive", "perceive()", (time.perf_counter() - t0) * 1000,
                       resp={"img_bytes": len(obs.image_png) if obs.image_png else 0, "state": obs.state})
        self._last_state = obs.state
        return obs

    def last_state(self) -> dict | None:
        """最近一次 perceive 到的 state(没感知过则 None)。给 /awi 仪表盘读。"""
        return self._last_state

    # ---------- 动作（可能很慢：生命迹象监督，不掐固定死线）----------
    def invoke(self, name: str, *, _on_progress: Optional[Callable] = None,
               _should_abort: Optional[Callable[[], bool]] = None, **kwargs: Any) -> ActionResult:
        """调世界的一个工具。慢动作按「生命迹象」等待：

        - `_on_progress(message, progress, total)`：可选，世界每报一次进度转发一次（对弈树用它发事件流）；
          不管传不传，进度都自动写 AWI 日志（仪表盘可见）。
        - `_should_abort() -> bool`：可选，返回 True 就放弃等待（取消/换局；粒度 0.25s 级）。
        带下划线是刻意的：这两个是**客户端旁路参数**，绝不会和世界工具自己的参数撞名。
        """
        if self._caps is None:
            self.capabilities()
        t0 = time.perf_counter()
        beat = mcp_bridge.Beat()

        async def _cb(progress: float, total, message) -> None:
            beat.touch()   # 进度 = 生命迹象，续命
            awi_log.record(self.name, "progress", f"{name}: {message or ''}",
                           (time.perf_counter() - t0) * 1000, resp={"progress": progress})
            if _on_progress is not None:
                try:
                    _on_progress(message or "", progress, total)
                except Exception:  # noqa: BLE001  上层回调坏了不该毁掉动作本身
                    pass

        async def op(s):
            r = await s.call_tool(name, kwargs, progress_callback=_cb)
            text = "".join(c.text for c in r.content if getattr(c, "text", None))
            data = r.structuredContent or {}
            ok = not bool(getattr(r, "isError", False))
            return ok, text, data

        try:
            ok, text, data = mcp_bridge.run_alive(
                with_session(self.mcp_url, op, config.WORLD_CONNECT_TIMEOUT,
                             read_timeout=config.WORLD_LIVENESS_TIMEOUT + config.BRIDGE_GRACE_S),
                beat=beat, liveness_s=config.WORLD_LIVENESS_TIMEOUT,
                hard_cap_s=config.WORLD_INVOKE_HARD_CAP, should_abort=_should_abort)
            res = ActionResult(ok=ok, message=text, data=data)
        except mcp_bridge.LivenessTimeout:
            res = ActionResult(False, f"世界失联：{config.WORLD_LIVENESS_TIMEOUT:g}s 无生命迹象")
        except mcp_bridge.HardCapTimeout:
            res = ActionResult(False, f"动作超总上限（{config.WORLD_INVOKE_HARD_CAP:g}s），放弃等待")
        except mcp_bridge.CallAborted:
            res = ActionResult(False, "已放弃等待（任务取消）")
        except Exception as e:
            res = ActionResult(False, f"（世界调用失败：{type(e).__name__}）")
        awi_log.record(self.name, "invoke", f"{name}({kwargs})", (time.perf_counter() - t0) * 1000,
                       resp={"ok": res.ok, "message": res.message, "has_data": bool(res.data)})
        return res

    # ---------- 带外（探活 / 上帝视角真值 / 直播）：始终普通 HTTP，与 MCP 无关 ----------
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
