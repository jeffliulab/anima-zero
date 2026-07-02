"""开发自测 CLI：进程内跑完整一轮对话，stdout 打回复 + 该轮的 Session Logs 流水（逐行 JSON）。

不依赖后端进程（只要目标世界/服务在跑），是 pytest（全假）与真网页（全真）之间的自测钩子：
    ./.venv/bin/python -m anima.dev_turn --world sim-chess --say "该你了，你执黑" --brain gpt-4.1-nano
    ./.venv/bin/python -m anima.dev_turn --say "你好"                    # 不连世界=纯聊天
    ./.venv/bin/python -m anima.dev_turn --world sim-chess --say "继续" --session s_xxx   # 在既有会话续一轮

会话真实落盘（memory/sessions/，网页里能看到），流水真实进 logs/sessions/——和正式链路同一套，
没有任何 mock；LLM key / 世界地址从 anima-zero/.env 读（同后端）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from dotenv import load_dotenv

from . import config, session_log
from .llm import DEFAULT_BRAIN, make_llm
from .orchestrator import Orchestrator
from .registry import WorldRegistry
from .session import SessionStore
from .session_log import LoggingLLM, session_scope


def main(argv: list[str] | None = None) -> int:
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))
    ap = argparse.ArgumentParser(description="跑一轮完整对话并 dump 该轮的 Session Logs 流水（开发自测用）")
    ap.add_argument("--say", required=True, help="用户这一轮说什么")
    ap.add_argument("--world", default=None, help="连哪个世界（config.worlds() 清单里的名字；不传=纯聊天）")
    ap.add_argument("--brain", default=DEFAULT_BRAIN, help=f"用哪个大脑（默认 {DEFAULT_BRAIN}）")
    ap.add_argument("--session", default=None, help="在既有会话上续一轮（不传=新建）")
    args = ap.parse_args(argv)

    registry = WorldRegistry()
    for name, url in config.worlds():
        registry.register_world(name, url)
    if args.world and registry.get(args.world) is None:
        print(f"未知世界：{args.world}（可选：{', '.join(n for n, _ in config.worlds())}）", file=sys.stderr)
        return 2

    store = SessionStore()
    if args.session and store.exists(args.session):
        session = store.get(args.session)
    else:
        session, _ = store.new(args.world, args.brain)
    llm = LoggingLLM(make_llm(session.brain), session.brain)   # 与后端同款收口包装

    orch = Orchestrator(registry, store)
    prior = session_log.recent(1, session=session.id)
    marker = (prior[-1].get("t", 0.0), prior[-1].get("id", 0)) if prior else (0.0, 0)
    with session_scope(session.id):
        out = orch.handle(session, args.say, llm)

    print(f"会话：{session.id}")
    print(f"回复：{out['reply']}\n")
    print("── 本轮 Session Logs 流水 ──")
    for e in session_log.recent(1000, session=session.id):
        if (e.get("t", 0.0), e.get("id", 0)) > marker:
            print(json.dumps(e, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
