"""AWI conformance: connect to a world and check it against the v1 contract.

一致性测试：连上一个世界，照 AWI v1 契约逐条核对。

Why this exists / 为什么要有这个
--------------------------------
The README's claim is that anyone can implement a world and ANIMA will drive it unchanged.
A claim like that is only worth something if the person who wrote a world can *find out*
whether they got it right — without reading this repository's source. So: one command.

README 的主张是"任何人写个世界，ANIMA 一行不改就能驱动它"。这种主张只有在**写世界的人自己能查出
来对没对**的时候才值钱——而且不该要求他去读我们的源码。所以：一条命令。

What this can and cannot tell you / 它能查什么、不能查什么
--------------------------------------------------------
It checks the **shape** of the contract: the channels exist, the types are right, the
ordering promise between named cameras and image blobs is kept, out-of-band stays out of
band.

它查的是契约的**形状**：通道在不在、类型对不对、多相机的名字顺序与图片顺序有没有对上、
带外的东西有没有跑到 AWI 上来。

⛔ It cannot check **truthfulness**, and does not pretend to. Whether a world's `state`
leaks a god's-eye view, whether `kind` matches what a tool really does, whether guidance is
honest — no automated check decides these. They are read by a person, at approval time.
That is the whole reason approval exists. See SECURITY.md §2.

⛔ 它查不了**真假**，也不假装能查。世界的 `state` 有没有泄露上帝视角、`kind` 和这个工具真实的
行为符不符、说明书写得诚不诚实——没有任何自动检查能定这些。它们由**人**在审批时读。
这正是审批存在的全部理由。见 SECURITY.md 第 2 节。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic import AnyUrl

from . import config
from .clients.mcp_bridge import run_sync, with_session
from .clients.world_client import CONFIG_URI, GUIDANCE_PROMPT, OBSERVATION_URI
from .core import trust
from .core.awi import NON_MUTATING_KINDS, ToolSpec

PASS, WARN, FAIL = "pass", "warn", "fail"

# A world that answers nothing within this many seconds is not going to pass anyway.
# 一个世界这么多秒都不应答，本来也过不了。
PROBE_TIMEOUT_S = config.WORLD_TIMEOUT


@dataclass
class Check:
    """One line of the report. `rule` points at the section of the spec it comes from.
    / 报告里的一行。`rule` 指向它出自规范的哪一节。"""

    status: str
    rule: str
    title: str
    detail: str = ""


@dataclass
class Report:
    url: str
    checks: list[Check] = field(default_factory=list)
    manifest_hash: str = ""
    state_keys: list[str] = field(default_factory=list)
    tool_names: list[str] = field(default_factory=list)

    def add(self, status: str, rule: str, title: str, detail: str = "") -> None:
        self.checks.append(Check(status, rule, title, detail))

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if c.status == FAIL]

    @property
    def warnings(self) -> list[Check]:
        return [c for c in self.checks if c.status == WARN]

    @property
    def conformant(self) -> bool:
        return not self.failures


# ---------------------------------------------------------------- the checks


def _check_tools(rep: Report, tools: list[Any]) -> None:
    """§3.1 Tools — declaration shape. / 工具通道：声明的形状。"""
    rep.tool_names = [t.name for t in tools]
    rep.add(PASS, "3.1", f"tools/list answered with {len(tools)} tool(s)",
            ", ".join(rep.tool_names) or "(none — valid for an observe-only world)")

    for t in tools:
        if not t.name:
            rep.add(FAIL, "3.1", "A tool has an empty name",
                    "The brain calls tools by name; an unnamed one is unreachable.")
            continue

        schema = t.inputSchema or {}
        if schema.get("type") != "object":
            rep.add(FAIL, "3.1", f"`{t.name}`: inputSchema is not an object schema",
                    f"Got type={schema.get('type')!r}. Tool arguments are named, so the "
                    f"schema must be `{{\"type\": \"object\", ...}}` even with no parameters.")

        desc = (t.description or "").strip()
        if not desc:
            rep.add(WARN, "3.1", f"`{t.name}` has no description",
                    "The description is how a model decides when to call this and when not "
                    "to. Without one it will be called at the wrong moments.")
        elif len(desc) > config.WORLD_TOOL_DESC_MAX_CHARS:
            rep.add(WARN, "5.2", f"`{t.name}`'s description exceeds the host's cap",
                    f"{len(desc)} chars against a cap of "
                    f"{config.WORLD_TOOL_DESC_MAX_CHARS}. ANIMA will truncate it and say so.")

        if t.annotations is None or t.annotations.readOnlyHint is None:
            rep.add(WARN, "3.1", f"`{t.name}` declares no readOnlyHint",
                    "Absent counts as not read-only, which is the safe reading. Declare it "
                    "so the operator sees what you intend this tool to be.")


def _check_observation(rep: Report, contents: list[Any]) -> None:
    """§3.2 Observation — state, images, and the ordering promise.
    / 感知通道：state、画面，以及顺序约定。"""
    if not contents:
        rep.add(FAIL, "3.2", "anima://observation returned nothing",
                "Every world must answer with at least a state object.")
        return

    head = contents[0]
    text = getattr(head, "text", None)
    if text is None:
        rep.add(FAIL, "3.2", "The first content of anima://observation is not text",
                "The state object comes first, as JSON text. Images follow it as blobs.")
        return

    try:
        state = json.loads(text)
    except json.JSONDecodeError as e:
        rep.add(FAIL, "3.2", "The state is not valid JSON", str(e))
        return

    if not isinstance(state, dict):
        rep.add(FAIL, "3.2", f"The state is a {type(state).__name__}, not an object",
                "State is a mapping of named readings. A bare list or string has no contract.")
        return

    rep.state_keys = sorted(state.keys())
    rep.add(PASS, "3.2", "anima://observation answered with a state object",
            ", ".join(rep.state_keys) or "(empty — valid: sim-chess deliberately gives {})")

    blobs = [c for c in contents[1:] if getattr(c, "blob", None) is not None
             or isinstance(getattr(c, "content", None), (bytes, bytearray))]
    non_png = [c for c in blobs if getattr(c, "mimeType", None) not in (None, "image/png")]
    if non_png:
        rep.add(FAIL, "3.2", "An image blob is not image/png",
                f"Got {[getattr(c, 'mimeType', None) for c in non_png]}. The brain decodes "
                f"PNG; anything else arrives as noise.")
    elif blobs:
        rep.add(PASS, "3.2", f"{len(blobs)} image blob(s), all image/png")
    else:
        rep.add(WARN, "3.2", "No image in the observation",
                "Valid — a world may have nothing to show, and ANIMA never fabricates a "
                "frame. But an embodied brain with no picture can only talk.")

    # ⭐ The one contract an automated check really can settle: multi-camera ordering.
    # MCP blobs carry no names, so the *order* is the correspondence. Get it wrong and the
    # brain silently attributes the wrong picture to the wrong camera — no error anywhere.
    # ⭐ 唯一一条自动检查真能定下来的契约：多相机的顺序。MCP 的 blob 本身不带名字，所以
    # **顺序就是对应关系**。错了的话大脑会把画面安在错的相机上——全程不报任何错。
    cameras = state.get("cameras")
    if isinstance(cameras, list) and cameras:
        if len(cameras) != len(blobs):
            rep.add(FAIL, "3.2", "state.cameras does not match the number of images",
                    f"{len(cameras)} camera name(s) {cameras} against {len(blobs)} image "
                    f"blob(s). Blobs carry no names, so their order is the only thing "
                    f"tying a picture to a camera. A mismatch means the brain attributes "
                    f"pictures to the wrong cameras, silently.")
        else:
            rep.add(PASS, "3.2", f"{len(cameras)} named cameras match {len(blobs)} images",
                    ", ".join(map(str, cameras)))


def _check_config(rep: Report, cfg: dict | None) -> None:
    """§3.4 Config — an optional declaration channel. / 世界配置：可选的声明通道。"""
    if cfg is None:
        rep.add(PASS, "3.4", "No anima://config (optional channel, absent)")
        return
    options = cfg.get("options")
    if not isinstance(options, list):
        rep.add(FAIL, "3.4", "anima://config has no `options` list",
                f"Shape must be {{\"options\": [...]}}; got keys {sorted(cfg)}.")
        return
    for i, opt in enumerate(options):
        if not isinstance(opt, dict) or "key" not in opt:
            rep.add(FAIL, "3.4", f"config option #{i} has no `key`", repr(opt)[:200])
            continue
        if "value" not in opt:
            rep.add(WARN, "3.4", f"config option `{opt['key']}` declares no current value",
                    "The panel shows what it is now; without `value` there is nothing to show.")
    rep.add(PASS, "3.4", f"anima://config declares {len(options)} option(s)",
            ", ".join(str(o.get("key")) for o in options if isinstance(o, dict)))


def _check_guidance(rep: Report, guidance: str) -> None:
    """§3.3 Guidance — and the fact that it lands in the system prompt.
    / 说明书——以及它会落进系统提示词这件事。"""
    if not guidance.strip():
        rep.add(WARN, "3.3", "No guidance prompt",
                "Valid, but the brain then meets your world with no idea what it is. This "
                "is what keeps ANIMA generic: the world describes itself.")
        return
    n = len(guidance)
    if n > config.WORLD_GUIDANCE_MAX_CHARS:
        rep.add(WARN, "5.2", "Guidance exceeds the host's cap",
                f"{n} chars against a cap of {config.WORLD_GUIDANCE_MAX_CHARS}. ANIMA "
                f"truncates it and tells the model it did.")
    else:
        rep.add(PASS, "3.3", f"Guidance present ({n} chars)")


def _check_out_of_band(rep: Report, base: str) -> None:
    """§4 Out-of-band HTTP — what must NOT be on AWI. / 带外：那些**不该**在 AWI 上的东西。"""
    with httpx.Client(timeout=config.WORLD_PROBE_TIMEOUT, follow_redirects=True) as c:
        try:
            r = c.get(base + "/health")
            if r.status_code == 200:
                rep.add(PASS, "4.1", "/health answers 200")
            else:
                rep.add(FAIL, "4.1", f"/health answered {r.status_code}",
                        "The online indicator polls this. Without it the world reads as "
                        "permanently offline, whatever else works.")
        except httpx.HTTPError as e:
            rep.add(FAIL, "4.1", "/health is unreachable", str(e))

        try:
            r = c.get(base + "/streams")
            entries = r.json() if r.status_code == 200 else None
        except (httpx.HTTPError, ValueError):
            entries = None

        if isinstance(entries, list) and len(entries) > 1:
            unmarked = [e.get("name", "?") for e in entries
                        if isinstance(e, dict) and "awi" not in e]
            if unmarked:
                rep.add(FAIL, "4.2", "Multiple streams, and some do not declare `awi`",
                        f"Unmarked: {unmarked}. The web page splits the sensor panel into "
                        f"'what ANIMA sees' and 'only you see this'. An unmarked spectator "
                        f"view is filed under the first heading, which tells the viewer the "
                        f"brain had a god's-eye view it did not have.")
            else:
                rep.add(PASS, "4.2", f"{len(entries)} streams, each declaring `awi`")


def _check_trust(rep: Report, url: str, tools: list[ToolSpec], guidance: str) -> None:
    """§6 Trust — what the operator will be asked to approve. / 信任：操作者将被要求批准的东西。"""
    m = trust.manifest(url, tools, guidance)
    rep.manifest_hash = trust.manifest_hash(m)
    mutating = [t.name for t in tools if t.kind not in NON_MUTATING_KINDS]
    rep.add(PASS, "6", "Manifest hash computed", rep.manifest_hash)
    if mutating:
        rep.add(PASS, "6", f"{len(mutating)} tool(s) declared as changing the world",
                ", ".join(mutating))


# ---------------------------------------------------------------- entry point


def _root_cause(e: BaseException, depth: int = 0) -> str:
    """The innermost real error, in words.

    anyio runs the MCP session in a task group, so a plain connection refusal surfaces as
    `ExceptionGroup: unhandled errors in a TaskGroup (1 sub-exception)` — which tells the
    one person this command is for, someone debugging their own world, nothing whatsoever.
    Unwrap to what actually went wrong.

    最里面那个真正的错误，说成人话。

    anyio 把 MCP 会话跑在一个 task group 里，所以"连接被拒绝"这种最普通的失败会以
    `ExceptionGroup: unhandled errors in a TaskGroup (1 sub-exception)` 的样子冒出来——
    而这条命令唯一的使用者、那个正在调自己世界的人，从这句话里什么都得不到。剥到真正出事的那层。
    """
    inner = getattr(e, "exceptions", None)
    if inner and depth < 5:                    # depth guard: nested groups, not infinite ones
        return "; ".join(_root_cause(x, depth + 1) for x in inner[:3])
    if e.__cause__ is not None and depth < 5:
        return _root_cause(e.__cause__, depth + 1)
    text = str(e).strip()
    return f"{type(e).__name__}: {text}" if text else type(e).__name__


def run(url: str, timeout: float = PROBE_TIMEOUT_S) -> Report:
    """Connect to `url` and check it against AWI v1. Never raises for a world's misbehaviour
    — a world that fails is a report, not an exception.
    / 连上 `url` 照 AWI v1 核对。世界表现不好不抛异常——那是一份报告，不是一个异常。"""
    base = url.rstrip("/")
    rep = Report(url=base)

    async def op(s):
        tl = await s.list_tools()
        guidance = ""
        try:
            pl = await s.list_prompts()
            if any(p.name == GUIDANCE_PROMPT for p in pl.prompts):
                gp = await s.get_prompt(GUIDANCE_PROMPT, {})
                guidance = "".join(m.content.text for m in gp.messages
                                   if getattr(m.content, "text", None))
        except Exception:
            pass

        uris, obs, cfg = set(), None, None
        try:
            rl = await s.list_resources()
            uris = {str(r.uri) for r in rl.resources}
        except Exception:
            pass
        if OBSERVATION_URI in uris:
            obs = (await s.read_resource(AnyUrl(OBSERVATION_URI))).contents
        if CONFIG_URI in uris:
            for c in (await s.read_resource(AnyUrl(CONFIG_URI))).contents:
                if getattr(c, "text", None):
                    cfg = json.loads(c.text)
                    break
            if cfg is None:
                cfg = {}
        return tl.tools, guidance, uris, obs, cfg

    try:
        tools, guidance, uris, obs, cfg = run_sync(
            with_session(base + "/mcp", op, timeout), timeout + config.BRIDGE_GRACE_S)
    except Exception as e:
        rep.add(FAIL, "2", "Could not complete an MCP handshake at /mcp",
                f"{_root_cause(e)}. AWI is MCP over Streamable HTTP mounted at /mcp. "
                f"Nothing else can be checked until this works.")
        return rep

    rep.add(PASS, "2", "MCP handshake at /mcp succeeded")
    _check_tools(rep, tools)

    if OBSERVATION_URI not in uris:
        rep.add(FAIL, "3.2", f"{OBSERVATION_URI} is not in resources/list",
                "Perception is the one required channel. A world ANIMA cannot look at is "
                "not a world it can be embodied in.")
    else:
        _check_observation(rep, obs or [])

    _check_guidance(rep, guidance)
    _check_config(rep, cfg)
    _check_out_of_band(rep, base)

    # Trust wants the brain's own ToolSpec shape, so the hash matches what approval records.
    # 信任那一步要的是大脑侧的 ToolSpec 形状，这样算出的哈希才和审批时记下的是同一个。
    specs = [ToolSpec(name=t.name, description=t.description or "",
                      parameters=t.inputSchema or {},
                      kind="read" if (t.annotations and t.annotations.readOnlyHint) else "tool")
             for t in tools]
    _check_trust(rep, base, specs, guidance)
    return rep


def format_report(rep: Report) -> str:
    """The report as a person reads it. / 给人读的报告。"""
    mark = {PASS: "✅", WARN: "⚠️ ", FAIL: "❌"}
    lines = [f"AWI v1 conformance — {rep.url}", ""]
    for c in rep.checks:
        lines.append(f"{mark[c.status]} §{c.rule}  {c.title}")
        if c.detail:
            lines.append(f"      {c.detail}")
    lines.append("")

    if rep.conformant:
        lines.append(f"Conformant. {len(rep.warnings)} recommendation(s) not followed."
                     if rep.warnings else "Conformant, with nothing to recommend.")
    else:
        lines.append(f"NOT conformant — {len(rep.failures)} failure(s), "
                     f"{len(rep.warnings)} recommendation(s) not followed.")

    # ⛔ Say plainly what this command did not check, every time. A green report that is
    # read as "this world is safe" is worse than no report.
    # ⛔ 每次都明说这条命令**没查**什么。一份被读成"这个世界安全"的绿报告，比没有报告更糟。
    lines += [
        "",
        "What this did not check — no automated check can:",
        "  · whether the state leaks a god's-eye view the brain should have to work out",
        "  · whether a tool's declared kind matches what it really does",
        "  · whether the guidance is honest, or is aimed at the model reading it",
        "Those are read by a person at approval time. Run `anima world add` and read it.",
    ]
    if rep.manifest_hash:
        lines.append(f"Manifest hash: {rep.manifest_hash}")
    return "\n".join(lines)
