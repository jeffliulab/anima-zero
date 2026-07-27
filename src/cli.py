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
import subprocess
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

BUILTIN_WORLD = "desk"
BUILTIN_WORLD_MODULE = "anima.worlds.desk"
BUILTIN_WORLD_PORT = 8114
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
    print("\nNothing configured? This still runs: anima demo")
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


def cmd_demo(args) -> int:
    """Install, one command, something happens — with no key and no world of your own.

    Starts the built-in world, approves it, and drops into a conversation with the brain
    that does not think. The point is not the conversation; it is that you can watch a
    frame, a decision, a tool call and a result go past.

    装完、一条命令、有事发生——不需要 key，也不需要你自己的世界。

    它起内置世界、批准它，然后进入一场和"不思考的大脑"的对话。重点不在对话本身，
    而在于你能亲眼看到一帧画面、一个决定、一次工具调用和一个结果走过去。
    """
    from .clients.world_client import RemoteWorld

    url = f"http://127.0.0.1:{args.port}"
    print(f"Starting the built-in world {BUILTIN_WORLD} at {url} …")
    proc = subprocess.Popen([sys.executable, "-m", BUILTIN_WORLD_MODULE,
                             "--port", str(args.port)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not _wait_for_health(url, timeout=20):
            print("The built-in world did not start.", file=sys.stderr)
            return 1

        # Approved without asking, and only this one. It ships in the same wheel as the
        # brain, so someone who installed the package has already made this decision;
        # asking again would train people to click through approvals that do matter.
        # 不问就批准，而且只批这一个。它和大脑装在同一个 wheel 里，所以装了这个包的人**已经**做过
        # 这个决定了；再问一遍只会训练人把真正要紧的审批也一路点过去。
        world = RemoteWorld(BUILTIN_WORLD, url)
        world.approve()

        store = SessionStore()
        session, _ = store.new(BUILTIN_WORLD, args.brain)
        reg = WorldRegistry()
        reg._worlds[BUILTIN_WORLD] = world
        llm = LoggingLLM(make_llm(args.brain), args.brain)
        orch = Orchestrator(reg, store)

        print(f"\nThe world is up. Brain: {args.brain}")
        if args.brain == "mock":
            print("(The mock brain does not think — it walks the chain end to end. Once a\n"
                  " key is configured, pick a real one with --brain.)")
        print(f"You can watch this world yourself: {url}/stream\n")
        print('Try saying something, such as "draw a block in the middle of the canvas".\n'
              "An empty line leaves.\n")

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
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("The built-in world has stopped.")
    return 0


# ===================================================================== parser / 入口 ===

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="anima", description="ANIMA — the brain of an embodied robot")
    ap.add_argument("--version", action="version", version=f"anima {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("demo", help="see it run, in one command (built-in world, no key needed)")
    p.add_argument("--brain", default="mock")
    p.add_argument("--port", type=int, default=BUILTIN_WORLD_PORT)
    p.set_defaults(fn=cmd_demo)

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

    p = sub.add_parser("conformance", help="check a world against the AWI v1 contract")
    p.add_argument("url", help="the world's base address, e.g. http://localhost:8100")
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
