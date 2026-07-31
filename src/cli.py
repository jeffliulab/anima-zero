"""`anima` — the command line.

## What this is for

A framework that can only be started with three `uvicorn` invocations and an `npm` command
is a framework you have to already understand before you can look at it. These commands
exist so that the first five minutes are: install, run one thing, see it work.

## The shape

The backend API is the single source of truth; the web app and this terminal are both just
clients of it. That mirrors what ANIMA itself claims — the brain does not know what a
frontend is — and it is why `anima chat` is not a lesser version of the web page but the
same system reached a different way.

`anima` —— 命令行。

## 它是干什么的

一个必须靠三条 `uvicorn` 加一条 `npm` 才能启动的框架，是**你得先看懂它才能开始看它**。这些命令的存在，
是为了让头五分钟变成：装上、跑一条命令、看到它工作。

## 形状

后端 API 是唯一真相，网页和这个终端都只是它的客户端。这和 ANIMA 自己的主张是一致的——大脑不知道
前端是什么——也正因如此，`anima chat` 不是网页的简化版，而是**同一个系统的另一个入口**。
"""
from __future__ import annotations

import argparse
import functools
import json
import sys
import time
import urllib.error
import urllib.request

from dotenv import load_dotenv

from . import config, conformance, paths
from ._version import __version__
from .clients.registry import WorldRegistry
from .core import trust
from .core.orchestrator import Orchestrator
from .llm import DEFAULT_BRAIN, list_brains, make_llm
from .session import SessionStore, session_log
from .session.session_log import LoggingLLM, session_scope

SERVE_HOST, SERVE_PORT = "127.0.0.1", 8000


# =============================================================== helpers / 小工具 ===

def _registry() -> WorldRegistry:
    reg = WorldRegistry()
    for name, url in config.worlds():
        reg.register_world(name, url)
    return reg


def _resolve_world(reg: WorldRegistry, name: str | None):
    if not name:
        return None
    w = reg.get(name)
    if w is None:
        known = ", ".join(n for n, _ in config.worlds()) or "(the list is empty)"
        raise SystemExit(f"No world named {name!r}. Registered: {known}")
    return w


def _wait_for_health(url: str, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url.rstrip("/") + "/health", timeout=1.0):
                return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.2)
    return False


def _print_manifest(world) -> None:
    """Everything a person needs in front of them before approving. The full guidance, not
    a summary — a review of an abridged text approves something that was never read.
    / 批准之前一个人需要摆在眼前的全部东西。**说明书是全文**，不是摘要——审阅一份删节版，
    等于批准了一个从没被读过的东西。"""
    raw = world.raw_capabilities()
    print(f"\nWorld:   {world.name}\nAddress: {world.base}")
    print(f"\nIt declares {len(raw.tools)} action(s):")
    for t in raw.tools:
        mark = "read-only" if t.kind in ("read", "judge") else "CHANGES THE WORLD"
        print(f"\n  · {t.name}   [{t.kind} / {mark}]")
        for line in (t.description or "(no description)").splitlines():
            print(f"      {line}")
    print(f"\nIts guidance — this is joined into the brain's system prompt "
          f"({len(raw.guidance)} chars):")
    print("  " + "\n  ".join((raw.guidance or "(no guidance)").splitlines()))


def _confirm(prompt: str) -> bool:
    try:
        return input(f"{prompt} [y/N] ").strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


# ================================================================= commands / 命令 ===

def cmd_world_list(args) -> int:
    reg, store = _registry(), trust.TrustStore()
    if trust.trust_all_enabled():
        print(f"⚠ {trust.TRUST_ALL_ENV} is on — every world is allowed and the approval\n"
              f"  status below does not apply. Development only.\n")
    rows = []
    for name, url in config.worlds():
        w = reg.get(name)
        online = w.online() if hasattr(w, "online") else False
        rec = store.approved_record(url.rstrip("/"))
        rows.append((name, url, "online" if online else "offline",
                     "approved" if rec else "not approved"))
    if not rows:
        print("The world list is empty. Add one with `anima world add <name> <url>`.")
        return 0
    w1 = max(len(r[0]) for r in rows)
    w2 = max(len(r[1]) for r in rows)
    for name, url, on, tr in rows:
        print(f"  {name:<{w1}}  {url:<{w2}}  {on}  {tr}")
    return 0


def cmd_world_add(args) -> int:
    """Register a world and review it in one go — because those are one decision.
    / 注册一个世界并当场审阅——因为这**本来就是一个决定**。"""
    from .clients.world_client import RemoteWorld

    url = args.url.rstrip("/")
    world = RemoteWorld(args.name, url)
    if not _wait_for_health(url, timeout=args.timeout):
        print(f"Cannot reach {url} — is it running?", file=sys.stderr)
        return 1
    try:
        _print_manifest(world)
    except Exception as e:
        print(f"Could not read this world's capabilities: {e}", file=sys.stderr)
        return 1

    print("\n⚠ Approve, and the text above enters the brain's system prompt and tool sheet.")
    print("  Only connect worlds you trust — SECURITY.md §2 says why.")
    if not (args.yes or _confirm("Approve this world?")):
        print("Not approved. The brain will not use it.")
        return 1
    world.approve()

    print("\nApproved. Add it to the world list — ANIMA_WORLDS in `.env`.\n"
          "⛔ Append; do not replace, or you drop the worlds already there:")
    existing = ",".join(f"{n}={u}" for n, u in config.worlds())
    print(f"  ANIMA_WORLDS={existing},{args.name}={url}")
    return 0


def cmd_world_remove(args) -> int:
    url = args.url_or_name.rstrip("/")
    if not url.startswith("http"):
        match = dict(config.worlds()).get(url)
        if match is None:
            print(f"No world named {url!r}.", file=sys.stderr)
            return 1
        url = match.rstrip("/")
    if trust.TrustStore().revoke(url):
        print(f"Approval for {url} revoked. Connecting again will ask you afresh.")
        return 0
    print(f"{url} was not approved in the first place.")
    return 0


def cmd_world_show(args) -> int:
    world = _resolve_world(_registry(), args.name)
    try:
        _print_manifest(world)
        d = world.trust_decision()
    except Exception as e:
        print(f"Cannot reach this world: {e}", file=sys.stderr)
        return 1
    print(f"\nTrust: {d.state}" + (f" ({d.reason})" if d.reason else ""))
    for line in d.changes:
        print(f"  {line}")
    return 0


# ---------------------------------------------------------------- demo / 演示 ===

DEMO_WORLD_NAME = "corridor-demo"
# The scripted first task. Kept short on purpose: the point of the first five minutes is
# watching the loop run — a task that takes fifteen steps teaches nothing that three do not.
DEMO_SAY = "Move the dot to the right end of the corridor."


def _pick_demo_brain(requested: str | None) -> str:
    """Which brain the demo runs on, decided out loud.

    Order: an explicit --brain → a configured online brain → the local CPU demo brain
    (Qwen3-4B via Ollama, pulling it if asked to) → the mock, with the three-step guide
    for getting the real one. Every step says what it picked and why: a demo that
    silently falls back teaches the wrong lesson.
    """
    import shutil
    import subprocess

    from .llm.factory import _ollama_tags

    if requested:
        return requested

    brains = {b["name"]: b for b in list_brains()}
    for name, b in brains.items():
        if b["hosting"] == "api" and b["available"]:
            print(f"Brain: {name} — you have its API key configured, so the demo uses "
                  f"the real thing.")
            return name

    model = config.MODEL_DEMO
    tags = _ollama_tags(config.OLLAMA_BASE_URL)
    ollama_up = bool(tags) or _ollama_reachable()
    if model in tags:
        print(f"Brain: demo — {model} on your local Ollama. No key, no cloud; "
              f"it really thinks, on your CPU.")
        return "demo"
    if ollama_up:
        print(f"Your Ollama is running but {model} is not pulled yet.")
        if _confirm("Pull it now? (~2.5 GB, one time, runs purely on CPU)"):
            rc = subprocess.run(["ollama", "pull", model]).returncode
            if rc == 0:
                print("Brain: demo — model pulled, using it.")
                return "demo"
            print("The pull failed; falling back to the mock brain for this run.")
    else:
        print("No API key and no local Ollama — the demo falls back to the mock brain,")
        print("which does NOT think: it only walks the chain so you can watch it.")
        print("\nFor a brain that actually thinks, free and offline:")
        if shutil.which("ollama"):
            print("  1. start Ollama:        ollama serve")
        else:
            print("  1. install Ollama:      https://ollama.com/download")
        print(f"  2. pull the demo brain: ollama pull {model}   (~2.5 GB, one time)")
        print("  3. run this again:      anima demo\n")
    return "mock"


def _ollama_reachable() -> bool:
    """Whether an Ollama server answers at all — `_ollama_tags` cannot tell 'server down'
    from 'zero models pulled', and the guidance to print differs between the two."""
    try:
        with urllib.request.urlopen(config.OLLAMA_BASE_URL.rstrip("/") + "/models",
                                    timeout=config.OLLAMA_PROBE_TIMEOUT) as r:
            return r.status == 200
    except Exception:
        return False


def cmd_demo(args) -> int:
    """Prove the whole loop works, against a world that ships inside the package.

    ROS has talker/listener; ANIMA has this. A corridor world starts on a free local
    port, a brain is picked (see _pick_demo_brain), and one scripted turn really runs —
    session on disk, trace in the logs, nothing staged.
    / 证明整条链路是活的——ROS 有 talker/listener，ANIMA 有这条命令。"""
    from .examples.minimal_world import serve_in_thread

    print("ANIMA demo — a dot on an eight-cell corridor, one brain, one real turn.")
    print("Everything you are about to see really happens: real session, real trace.\n")

    brain = _pick_demo_brain(args.brain)
    try:
        make_llm(brain)     # validate now rather than mid-turn
    except KeyError as e:
        print(str(e), file=sys.stderr)
        return 1

    with serve_in_thread() as base:
        reg = WorldRegistry()
        reg.register_world(DEMO_WORLD_NAME, base)
        world = reg.get(DEMO_WORLD_NAME)

        # The trust flow, exercised honestly rather than bypassed: a world's text never
        # reaches the brain unapproved, so the demo approves — and says that normally
        # this is the step where a person reads the manifest first. The approval is
        # revoked on the way out: the port is ephemeral, and a stale entry in the trust
        # store would approve nothing but clutter it forever.
        print(f"\nWorld: {DEMO_WORLD_NAME} on {base} (started just now, inside this process)")
        print("Approving it for this run — normally YOU review the manifest first; that")
        print("review is what `anima world add` walks you through for any other world.")
        world.approve()

        store = SessionStore()
        session, _ = store.new(DEMO_WORLD_NAME, brain)
        llm = LoggingLLM(make_llm(session.brain), session.brain)
        orch = Orchestrator(reg, store)

        print(f"\nTask: {args.say!r}   (brain: {brain}, session: {session.id})")
        print("Thinking... (a local CPU brain can take a few seconds per step)\n")
        try:
            with session_scope(session.id):
                out = orch.handle(session, args.say, llm)
        finally:
            # 审批是这轮临时给的，走完就还回去——端口每次都换，留着只会把信任库堆满死条目。
            trust.TrustStore().revoke(base)

        print(f"ANIMA › {out['reply']}\n")
        log = session_log._file_for(session.id)
        print(f"Every frame, thought and tool call of that turn is in:\n  {log}")

    print("\nNext steps:")
    print("  · same world, your pace:  python -m anima.examples.minimal_world --port 8090")
    print("    then:                   anima world add example http://localhost:8090")
    print("  · talk to it:             anima chat --world example")
    print("  · the web app:            anima serve")
    print("  · write your own world:   src/examples/minimal_world.py is the template,")
    print("                            docs/awi-spec-v1.md is the contract it follows")
    return 0


def cmd_doctor(args) -> int:
    """What is configured, what is reachable, and what would happen if you ran something.
    / 什么配好了、什么连得上、以及你现在跑一条命令会发生什么。"""
    print(f"anima {__version__}   python {sys.version.split()[0]}")
    print(f"settings  {paths.ENV_FILE}"
          + ("" if paths.ENV_FILE and _exists(paths.ENV_FILE) else "  (does not exist)"))
    print(f"trust     {trust.TrustStore().path}")
    if trust.trust_all_enabled():
        print(f"⚠ {trust.TRUST_ALL_ENV} is on — every world allowed. Development only.")

    print("\nBrains:")
    for b in list_brains():
        print(f"  {'✓' if b['available'] else '·'} {b['name']:<14} {b['label']}"
              + ("" if b["available"] else "   (not configured — no key, or model not pulled)"))

    print("\nWorlds:")
    reg, store = _registry(), trust.TrustStore()
    # 逃生门开着时不说"大脑用不了它"——那是假的，开着的时候大脑用得了。
    # 一份自相矛盾的诊断比没有诊断更糟：它会教人不信这份输出。
    bypass = trust.trust_all_enabled()
    for name, url in config.worlds():
        w = reg.get(name)
        online = w.online() if hasattr(w, "online") else False
        approved = store.approved_record(url.rstrip("/")) is not None
        note = ""
        if not online:
            note = "   (offline)"
        elif not approved:
            note = ("   (not approved, but the escape hatch is on, so usable)" if bypass
                    else "   (not approved — the brain cannot use it)")
        print(f"  {'✓' if online else '·'} {name:<16} {url}{note}")
    # No worlds is the normal state after `pip install`: worlds are separate programs and
    # none of them ships in the wheel. Say where to get one rather than leaving an empty list.
    # 装完包之后"一个世界都没有"是正常状态：世界是独立的程序，wheel 里一个都不带。
    # 与其留一张空清单，不如说清楚去哪弄一个。
    if not config.worlds():
        print("  (none — a world is a separate program; clone the repository for the ones in "
              "world/, or write your own against docs/awi-spec-v1.md)")
        print("  Want to see it move first? `anima demo` starts a bundled world and runs one turn.")
    print("\nRegister one with: anima world add NAME URL")
    return 0


def _exists(path: str) -> bool:
    import os
    return os.path.exists(path)


def cmd_conformance(args) -> int:
    """Check a world against AWI v1 — for people writing worlds, who should not have to read
    this repository's source to find out whether they got the contract right.

    Exit code is 0 when conformant. Recommendations do not fail the run: a world with no
    guidance is unhelpful but not non-conformant, and blurring the two would make the
    distinction worthless.

    照 AWI v1 核对一个世界——给写世界的人用，他不该为了知道自己有没有写对而去读我们的源码。

    合规则退出码 0。**建议不算失败**：一个没有说明书的世界是不好用，但它并不违规；
    把两者混为一谈，这个区分就白做了。"""
    rep = conformance.run(args.url, timeout=args.timeout)
    print(conformance.format_report(rep))
    return 0 if rep.conformant else 1


def cmd_run(args) -> int:
    """One turn, scripted. Everything really happens — real session on disk, real trace.
    / 单轮、可脚本化。全都是真的——会话真落盘、流水真产生。"""
    reg = _registry()
    _resolve_world(reg, args.world)
    store = SessionStore()
    session = (store.get(args.session) if args.session and store.exists(args.session)
               else store.new(args.world, args.brain)[0])
    llm = LoggingLLM(make_llm(session.brain), session.brain)
    orch = Orchestrator(reg, store)

    prior = session_log.recent(1, session=session.id)
    marker = (prior[-1].get("t", 0.0), prior[-1].get("id", 0)) if prior else (0.0, 0)
    with session_scope(session.id):
        out = orch.handle(session, args.say, llm)

    print(f"session: {session.id}")
    print(f"reply:   {out['reply']}")
    if args.trace:
        print("\n── trace for this turn ──")
        for e in session_log.recent(1000, session=session.id):
            if (e.get("t", 0.0), e.get("id", 0)) > marker:
                print(json.dumps(e, ensure_ascii=False))
    return 0


def cmd_chat(args) -> int:
    """A conversation in the terminal. No browser, no node.
    / 在终端里对话。不需要浏览器，不需要 node。"""
    reg = _registry()
    _resolve_world(reg, args.world)
    store = SessionStore()
    session, _ = store.new(args.world, args.brain)
    llm = LoggingLLM(make_llm(session.brain), session.brain)
    orch = Orchestrator(reg, store)

    where = f"world {args.world}" if args.world else "no world (chat only)"
    print(f"anima chat · brain {args.brain} · {where} · session {session.id}")
    print("Just type. Ctrl-C or an empty line to leave.\n")
    while True:
        try:
            text = input("you › ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            break
        with session_scope(session.id):
            out = orch.handle(session, text, llm)
        print(f"\nANIMA › {out['reply']}\n")
    print(f"Session {session.id} is kept — continue it with "
          f"`anima run --session {session.id} --say ...`")
    return 0


def cmd_serve(args) -> int:
    import uvicorn

    from .presentation.server import ui_build_time

    # flush=True on every line below. Python block-buffers stdout when it is not a terminal,
    # so `anima serve > log` would show nothing until the buffer filled — and a server that
    # looks silent on startup looks broken.
    # 下面每一行都 flush=True。stdout 不是终端时 Python 会块缓冲，于是 `anima serve > log`
    # 在缓冲区填满之前什么都不显示——而一个"启动时一声不响"的服务，看起来就是坏的。
    say = functools.partial(print, flush=True)

    url = f"http://{args.host}:{args.port}"
    built = ui_build_time()
    if built:
        # The build time is printed rather than just "web app: yes". A wheel packaged
        # without rebuilding the UI ships a stale copy silently, and a stale interface is
        # indistinguishable from a working one — a date is the cheapest way to catch it.
        # 打印的是构建时间而不是"网页：有"。打包时忘了重建网页会**静默**发出一份旧的，
        # 而过时的界面和正常的界面看起来一模一样——一个日期是最便宜的发现办法。
        say(f"web + API   {url}   (web app built {built})")
    else:
        say(f"API   {url}")
        say("No web app in this install. For development: cd frontend && npm run dev")
        say("To bundle it in: python scripts/build_ui.py")
    if args.host not in ("127.0.0.1", "localhost"):
        say(f"⚠ Bound to {args.host} — anyone on this network can open a session and\n"
            f"  drive whatever world you have connected.")
    uvicorn.run("anima.presentation.server:app", host=args.host, port=args.port,
                log_level="warning")
    return 0


# ===================================================================== parser / 入口 ===

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="anima", description="ANIMA — the brain of an embodied robot")
    ap.add_argument("--version", action="version", version=f"anima {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("chat", help="talk to it in the terminal")
    p.add_argument("--world", default=None)
    p.add_argument("--brain", default=DEFAULT_BRAIN)
    p.set_defaults(fn=cmd_chat)

    p = sub.add_parser("run", help="one turn, then exit (scriptable)")
    p.add_argument("--say", required=True)
    p.add_argument("--world", default=None)
    p.add_argument("--brain", default=DEFAULT_BRAIN)
    p.add_argument("--session", default=None, help="continue an existing session")
    p.add_argument("--trace", action="store_true", help="print this turn's trace as well")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("serve", help="start the backend API")
    p.add_argument("--host", default=SERVE_HOST,
                   help="this machine only by default. Setting 0.0.0.0 lets anyone on the "
                        "network drive whatever world you have connected.")
    p.add_argument("--port", type=int, default=SERVE_PORT)
    p.set_defaults(fn=cmd_serve)

    p = sub.add_parser("doctor", help="what is configured, and what is reachable")
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser("demo", help="prove the loop works: a bundled world, one brain, one real turn")
    p.add_argument("--brain", default=None,
                   help="force a brain (default: an online key if configured, else the "
                        "local CPU demo brain, else the mock)")
    p.add_argument("--say", default=DEMO_SAY,
                   help="the scripted task (default: %(default)r)")
    p.set_defaults(fn=cmd_demo)

    p = sub.add_parser("conformance", help="check a world against the AWI v1 contract")
    p.add_argument("url", help="the world's base address, e.g. http://localhost:8102")
    p.add_argument("--timeout", type=float, default=conformance.PROBE_TIMEOUT_S)
    p.set_defaults(fn=cmd_conformance)

    w = sub.add_parser("world", help="register and approve worlds").add_subparsers(
        dest="wcmd", required=True)
    q = w.add_parser("list", help="the world list, with online and approval status")
    q.set_defaults(fn=cmd_world_list)
    q = w.add_parser("add", help="register a world: see everything it declares, then decide")
    q.add_argument("name")
    q.add_argument("url")
    q.add_argument("--yes", action="store_true",
                   help="⚠ approve without reading (for scripts; not for ordinary use)")
    q.add_argument("--timeout", type=float, default=10.0)
    q.set_defaults(fn=cmd_world_add)
    q = w.add_parser("show", help="what a world declares, and its trust status")
    q.add_argument("name")
    q.set_defaults(fn=cmd_world_show)
    q = w.add_parser("remove", help="revoke approval for a world")
    q.add_argument("url_or_name")
    q.set_defaults(fn=cmd_world_remove)
    return ap


def main(argv: list[str] | None = None) -> int:
    load_dotenv(paths.ENV_FILE)
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except KeyboardInterrupt:
        print()
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
