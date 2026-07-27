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

from .. import awi_log, config
from . import mcp_bridge
from ..core.awi import ActionResult, Capabilities, Observation, ToolSpec
from ..core import trust
from .mcp_bridge import run_sync, with_session

DEFAULT_TIMEOUT = config.WORLD_TIMEOUT       # 读操作（capabilities/perceive）的死线（config，env 可覆盖）
ONLINE_PROBE_TIMEOUT = config.WORLD_PROBE_TIMEOUT  # 探在线的短超时

# MCP 契约常量（世界侧适配器 awi_mcp.py 用同样的字符串，两边必须一致）。
OBSERVATION_URI = "anima://observation"   # 感知资源：读它拿到 state(text) + 画面(image/png blob)
CONFIG_URI = "anima://config"             # 世界配置资源：世界声明它能配什么、现在是什么
GUIDANCE_PROMPT = "guidance"              # 说明书提示词名


class RemoteWorld:  # 实现 World 协议(AWI 客户端)
    def __init__(self, name: str, base_url: str, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.name = name
        self.base = base_url.rstrip("/")
        self.mcp_url = self.base + "/mcp"
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)  # 带外专用(/health /status /stream)
        self._caps: Capabilities | None = None    # 能力缓存:握手一次,之后复用
        self._raw_caps: Capabilities | None = None  # 未经信任过滤的原件(审批界面看的是它)
        self._trust: trust.TrustDecision | None = None
        self._last_state: dict | None = None       # 最近一次 perceive 的 state(给 /awi 仪表盘看)

    # ---------- 信任（v1.1）----------
    def trust_decision(self) -> trust.TrustDecision:
        """这个世界被审批过吗？没握过手就先握一次（要拿到清单才能问这个问题）。
        / Has this world been approved? Handshakes first if needed — the question cannot be
        answered without the manifest."""
        self.capabilities()
        return self._trust

    def raw_capabilities(self) -> Capabilities:
        """世界**原样**声明的能力，未经信任过滤。

        ⛔ 只给审批界面用。给人看的必须是完整原文——如果审批时看到的是过滤后的版本，
        那这次审批就没有意义了。绝不要拿它去喂大脑。

        ⛔ For the approval UI only. What a human approves has to be the complete text; if
        the review showed a filtered version the approval would mean nothing. Never feed
        this to the brain."""
        self.capabilities()
        return self._raw_caps

    def approve(self, store: trust.TrustStore | None = None) -> str:
        """记下操作者对当前这份清单的批准，并让下一次握手重新判定。
        / Record the operator's approval of the manifest as it stands now."""
        raw = self.raw_capabilities()
        h = (store or trust.TrustStore()).approve(self.base, raw.tools, raw.guidance, self.name)
        self._caps = self._raw_caps = self._trust = None      # 下次握手按新状态重算
        return h

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
            # 世界配置（可选通道）：世界没声明就读不到，读不到就是没有——不是错误，别让它挂掉握手。
            cfg: dict = {}
            try:
                rl = await s.list_resources()
                if any(str(r.uri) == CONFIG_URI for r in rl.resources):
                    rd = await s.read_resource(AnyUrl(CONFIG_URI))
                    for c in rd.contents:
                        if getattr(c, "text", None):
                            cfg = json.loads(c.text) or {}
                            break
            except Exception:
                pass
            return tools, guidance, cfg

        t0 = time.perf_counter()
        tools, guidance, cfg = run_sync(with_session(self.mcp_url, op, self.timeout),
                                        self.timeout + config.BRIDGE_GRACE_S)
        self._raw_caps = Capabilities(name=self.name, version="", tools=tools, state_schema={},
                                      guidance=guidance, config=cfg)

        # ⛔ 信任闸：世界写的工具与说明书，在被操作者审批之前**不进大脑**。
        # 未批准时返回一份「空能力」——世界仍然列得出来、状态看得见（前端要能显示"待批准"并让人去批），
        # 但它的文本不会进系统提示词、它的工具不会进工具单。
        # 不抛异常是有意的：抛异常会让整条链路挂掉，而"这个世界还没批"是一个**正常状态**，不是错误。
        #
        # ⛔ Trust gate: a world's tools and guidance do not reach the brain until the
        # operator has approved them. An unapproved world returns empty capabilities — it
        # still lists, and its state is still visible so the UI can offer approval — but its
        # text never enters the system prompt and its tools never enter the tool sheet.
        # Deliberately not an exception: "not approved yet" is a normal state, not a failure.
        self._trust = trust.TrustStore().check(self.base, tools, guidance)
        if self._trust.allowed:
            self._caps = self._raw_caps
        else:
            self._caps = Capabilities(name=self.name, version="", tools=[], state_schema={},
                                      guidance="", config=cfg)

        awi_log.record(self.name, "capabilities", "capabilities() handshake [mcp]",
                       (time.perf_counter() - t0) * 1000,
                       resp={"transport": "mcp", "n_tools": len(tools),
                             "tools": [t.name for t in tools], "has_guidance": bool(guidance),
                             "config": cfg.get("options", [])})
        return self._caps

    def refresh(self) -> None:
        """丢掉能力缓存,下次 capabilities() 重新握手(世界换了工具 / 重启后用)。

        ⛔ 三份缓存必须一起丢。只丢 `_caps` 会留下一个**过时的信任判定**——世界改了工具之后，
        重新握手拿到新清单，却拿旧判定去放行它，rug pull 就从这个缝里过去了。
        ⛔ All three must go together: dropping only `_caps` would leave a stale trust
        decision, and a rug pull would walk straight through that gap."""
        self._caps = self._raw_caps = self._trust = None

    # ---------- 世界配置：读走 AWI（握手时一起拿），改走带外 HTTP ----------
    def set_config(self, key: str, value: str) -> dict:
        """改这个世界的一项配置（如换身体）。

        ⚠️ **走带外普通 HTTP，不走 MCP**——和 `/status`、`/reset` 一个类别。
        理由：改配置是**人**的动作，不是大脑的动作；MCP 那条线是脑↔世界的，
        把人的操作塞进去会让大脑以为自己能改（它没有对应的工具，说了只会去调不存在的东西）。
        """
        try:
            r = self._client.post(self.base + "/config", json={"key": key, "value": value},
                                  timeout=config.WORLD_STATUS_TIMEOUT)
            return r.json()
        except Exception as e:
            return {"ok": False, "message": f"The world `{self.name}` did not answer — is it running? {e}"}

    # ---------- 感知（快速读，固定死线）----------
    def perceive(self) -> Observation:
        async def op(s):
            rd = await s.read_resource(AnyUrl(OBSERVATION_URI))
            state: dict = {}
            blobs: list[bytes] = []
            for c in rd.contents:
                if getattr(c, "text", None) is not None:
                    try:
                        state = json.loads(c.text) or {}
                    except Exception:
                        state = {}
                elif getattr(c, "blob", None) is not None:
                    blobs.append(base64.b64decode(c.blob))
            return state, blobs

        t0 = time.perf_counter()
        try:
            state, blobs = run_sync(with_session(self.mcp_url, op, self.timeout),
                                    self.timeout + config.BRIDGE_GRACE_S)
        except Exception:
            state, blobs = {}, []
        # 多相机对应关系：state["cameras"] 的名字顺序 = blob 顺序（契约见 awi_mcp.py）；
        # 世界没给名字（单相机老形状）→ 名字空串。image_png = 第一张（主图，向后兼容）。
        names = state.get("cameras") if isinstance(state.get("cameras"), list) else []
        images = [{"name": (names[i] if i < len(names) else ""), "png": b}
                  for i, b in enumerate(blobs)]
        obs = Observation(image_png=blobs[0] if blobs else None, state=state, images=images)
        awi_log.record(self.name, "perceive", "perceive()", (time.perf_counter() - t0) * 1000,
                       resp={"img_bytes": sum(len(b) for b in blobs), "n_images": len(blobs),
                             "cameras": [i["name"] for i in images if i["name"]], "state": obs.state})
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
            res = ActionResult(False, f"Lost contact with the world: no sign of life for "
                                          f"{config.WORLD_LIVENESS_TIMEOUT:g}s")
        except mcp_bridge.HardCapTimeout:
            res = ActionResult(False, f"The action exceeded its overall cap of "
                                          f"{config.WORLD_INVOKE_HARD_CAP:g}s; gave up waiting")
        except mcp_bridge.CallAborted:
            res = ActionResult(False, "Gave up waiting (the task was cancelled)")
        except Exception as e:
            res = ActionResult(False, f"(The call to the world failed: {type(e).__name__})")
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
