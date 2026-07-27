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

from . import config, paths
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
        known = ", ".join(n for n, _ in config.worlds()) or "(清单是空的)"
        raise SystemExit(f"没有名叫「{name}」的世界。已登记的：{known}")
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
    print(f"\n世界：{world.name}\n地址：{world.base}")
    print(f"\n它声明了 {len(raw.tools)} 个动作：")
    for t in raw.tools:
        mark = "只读" if t.kind in ("read", "judge") else "会改变世界"
        print(f"\n  · {t.name}   [{t.kind} / {mark}]")
        for line in (t.description or "(没有描述)").splitlines():
            print(f"      {line}")
    print(f"\n它的说明书（会被拼进大脑的系统提示词，共 {len(raw.guidance)} 字）：")
    print("  " + "\n  ".join((raw.guidance or "(没有说明书)").splitlines()))


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
        print(f"⚠ {trust.TRUST_ALL_ENV} 开着——全部世界一律放行，下面的审批状态不生效（仅限开发）\n")
    rows = []
    for name, url in config.worlds():
        w = reg.get(name)
        online = w.online() if hasattr(w, "online") else False
        rec = store.approved_record(url.rstrip("/"))
        rows.append((name, url, "在线" if online else "离线",
                     "已批准" if rec else "未批准"))
    if not rows:
        print("世界清单是空的。用 `anima world add <名字> <地址>` 加一个。")
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
        print(f"连不上 {url}（它起来了吗？）", file=sys.stderr)
        return 1
    try:
        _print_manifest(world)
    except Exception as e:
        print(f"取不到这个世界的能力清单：{e}", file=sys.stderr)
        return 1

    print("\n⚠ 批准之后，上面这些文字会进入大脑的系统提示词和工具单。")
    print("  只批准你信任的世界——理由见 SECURITY.md 第 2 节。")
    if not (args.yes or _confirm("批准这个世界？")):
        print("没有批准。它不会被大脑使用。")
        return 1
    world.approve()

    print("\n已批准。把它加进世界清单（`.env` 的 ANIMA_WORLDS，⛔ 是追加不是替换）：")
    existing = ",".join(f"{n}={u}" for n, u in config.worlds())
    print(f"  ANIMA_WORLDS={existing},{args.name}={url}")
    return 0


def cmd_world_remove(args) -> int:
    url = args.url_or_name.rstrip("/")
    if not url.startswith("http"):
        match = dict(config.worlds()).get(url)
        if match is None:
            print(f"没有名叫「{url}」的世界。", file=sys.stderr)
            return 1
        url = match.rstrip("/")
    if trust.TrustStore().revoke(url):
        print(f"已撤销对 {url} 的批准。下次连它会重新问你。")
        return 0
    print(f"{url} 本来就没有被批准过。")
    return 0


def cmd_world_show(args) -> int:
    world = _resolve_world(_registry(), args.name)
    try:
        _print_manifest(world)
        d = world.trust_decision()
    except Exception as e:
        print(f"连不上这个世界：{e}", file=sys.stderr)
        return 1
    print(f"\n信任状态：{d.state}" + (f"（{d.reason}）" if d.reason else ""))
    for line in d.changes:
        print(f"  {line}")
    return 0


def cmd_doctor(args) -> int:
    """What is configured, what is reachable, and what would happen if you ran something.
    / 什么配好了、什么连得上、以及你现在跑一条命令会发生什么。"""
    print(f"anima {__version__}   python {sys.version.split()[0]}")
    print(f"配置文件  {paths.ENV_FILE}" + ("" if paths.ENV_FILE and _exists(paths.ENV_FILE) else "  (不存在)"))
    print(f"信任记录  {trust.TrustStore().path}")
    if trust.trust_all_enabled():
        print(f"⚠ {trust.TRUST_ALL_ENV} 开着——全部世界一律放行（仅限开发）")

    print("\n大脑：")
    for b in list_brains():
        print(f"  {'✓' if b['available'] else '·'} {b['name']:<14} {b['label']}"
              + ("" if b["available"] else "   （没配好，缺 key 或模型没拉）"))

    print("\n世界：")
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
            note = "   （离线）"
        elif not approved:
            note = "   （未批准，但逃生门开着，照样能用）" if bypass else "   （未批准，大脑用不了它）"
        print(f"  {'✓' if online else '·'} {name:<16} {url}{note}")
    print("\n什么都没配好也能跑：anima demo")
    return 0


def _exists(path: str) -> bool:
    import os
    return os.path.exists(path)


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

    print(f"会话：{session.id}")
    print(f"回复：{out['reply']}")
    if args.trace:
        print("\n── 本轮流水 ──")
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

    where = f"世界 {args.world}" if args.world else "纯聊天（没连世界）"
    print(f"anima chat · 大脑 {args.brain} · {where} · 会话 {session.id}")
    print("直接说话；Ctrl-C 或空行退出。\n")
    while True:
        try:
            text = input("你 › ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            break
        with session_scope(session.id):
            out = orch.handle(session, text, llm)
        print(f"\nANIMA › {out['reply']}\n")
    print(f"会话留在 {session.id}——`anima run --session {session.id} --say ...` 可以续。")
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
        say(f"网页 + API   {url}   （网页构建于 {built}）")
    else:
        say(f"API   {url}")
        say("这个装法里没有带网页。开发时另起：cd frontend && npm run dev")
        say("要把网页装进来：python scripts/build_ui.py")
    if args.host not in ("127.0.0.1", "localhost"):
        say(f"⚠ 绑在 {args.host} 上——同网段的人都能建会话、驱动你连着的世界。")
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
    print(f"起内置世界 {BUILTIN_WORLD}（{url}）…")
    proc = subprocess.Popen([sys.executable, "-m", BUILTIN_WORLD_MODULE,
                             "--port", str(args.port)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not _wait_for_health(url, timeout=20):
            print("内置世界没起来。", file=sys.stderr)
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

        print(f"\n世界起来了。大脑：{args.brain}")
        if args.brain == "mock":
            print("（mock 大脑不思考——它只是把链路走一遍。配了 key 之后用 --brain 换一个真的。）")
        print(f"人也可以自己看这个世界：{url}/stream\n")
        print("说点什么试试，比如「在画布中间画一块」。空行退出。\n")

        while True:
            try:
                text = input("你 › ").strip()
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
        print("内置世界已停。")
    return 0


# ===================================================================== parser / 入口 ===

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="anima", description="ANIMA —— 具身机器人的大脑")
    ap.add_argument("--version", action="version", version=f"anima {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("demo", help="一条命令看它跑起来（内置世界 + 不用 key 的大脑）")
    p.add_argument("--brain", default="mock")
    p.add_argument("--port", type=int, default=BUILTIN_WORLD_PORT)
    p.set_defaults(fn=cmd_demo)

    p = sub.add_parser("chat", help="在终端里跟它对话")
    p.add_argument("--world", default=None)
    p.add_argument("--brain", default=DEFAULT_BRAIN)
    p.set_defaults(fn=cmd_chat)

    p = sub.add_parser("run", help="跑一轮就退出（可脚本化）")
    p.add_argument("--say", required=True)
    p.add_argument("--world", default=None)
    p.add_argument("--brain", default=DEFAULT_BRAIN)
    p.add_argument("--session", default=None, help="在既有会话上续一轮")
    p.add_argument("--trace", action="store_true", help="连本轮流水一起打出来")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("serve", help="起后端 API")
    p.add_argument("--host", default=SERVE_HOST,
                   help="默认只对本机。改成 0.0.0.0 等于让同网段的人都能驱动你连着的世界。")
    p.add_argument("--port", type=int, default=SERVE_PORT)
    p.set_defaults(fn=cmd_serve)

    p = sub.add_parser("doctor", help="看什么配好了、什么连得上")
    p.set_defaults(fn=cmd_doctor)

    w = sub.add_parser("world", help="登记与审批世界").add_subparsers(dest="wcmd", required=True)
    q = w.add_parser("list", help="世界清单 + 在线与审批状态")
    q.set_defaults(fn=cmd_world_list)
    q = w.add_parser("add", help="登记一个世界：先摊开它声明了什么，再由你决定批不批")
    q.add_argument("name")
    q.add_argument("url")
    q.add_argument("--yes", action="store_true", help="⚠ 不看就批准（脚本用；平时别用）")
    q.add_argument("--timeout", type=float, default=10.0)
    q.set_defaults(fn=cmd_world_add)
    q = w.add_parser("show", help="看一个世界声明了什么 + 它的信任状态")
    q.add_argument("name")
    q.set_defaults(fn=cmd_world_show)
    q = w.add_parser("remove", help="撤销对一个世界的批准")
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
