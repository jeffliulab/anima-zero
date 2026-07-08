"""AWI 流量记账(ANIMA 端):记录每一次脑↔世界 / 脑↔引擎的调用,给 /awi 仪表盘的实时 terminal + 统计用。

这是把「AWI 这套接口」(现经 **MCP**)可视化:谁(哪个 server:世界 or 引擎)被调了什么、耗时多少。
world 的 capabilities / perceive / invoke、engine 的 best_move（world 字段记成 "chess-engine"）都会出现在这里。
"""
from __future__ import annotations

import json
import os
import time
from collections import deque

from . import config, paths
from .session import session_log

# 脑端保留多少条 AWI 流量历史（config，env 可覆盖）。世界端有自己的同名 env;前端显示数须 ≤ 此值。
AWI_LOG_MAXLEN = config.AWI_LOG_MAXLEN
_LOG: deque = deque(maxlen=AWI_LOG_MAXLEN)
_SEQ = 0

# 除了内存(给 /awi 仪表盘实时看),每条流量也落到本地文件,方便追溯历史。
# 一天一个文件:logs/awi-YYYY-MM-DD.jsonl,每行一条 JSON。logs/ 已在 .gitignore,不入库、不 push。
_LOG_DIR = paths.LOGS_DIR


def _persist(entry: dict) -> None:
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        path = os.path.join(_LOG_DIR, "awi-" + time.strftime("%Y-%m-%d") + ".jsonl")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # 落盘失败绝不能影响主流程


def record(world: str, method: str, summary: str, ms: float, resp: dict | None = None,
           kind: str = "world_call") -> None:
    """记一笔脑↔世界（或脑↔服务，kind="service_call"）的往返。
    - summary：出方向(ANIMA→server)发了什么(方法+参数)。
    - resp：回方向(server→ANIMA)返回的【结构化】信息(图片字节数、ok/message、回程 state…)。
      给 /awi 仪表盘双向展示用，也是审计点：世界违约偷传棋盘真值(FEN/legal_moves)在这能看出来。
    每条同时**转发一份进 session_log**（统一日志=单一真相，本文件的内存 deque + 日文件只是
    /awi 实时区与 eval 的投影）；session 标签由 session_log 的请求级上下文自动带上。
    """
    global _SEQ
    _SEQ += 1
    entry = {
        "id": _SEQ,
        "ts": time.strftime("%H:%M:%S"),
        "session": session_log.current_session(),   # 归属会话（空=非会话场景，如探活）
        "world": world,
        "method": method,
        "summary": summary,        # 出方向(ANIMA→server)
        "resp": resp or {},        # 回方向(server→ANIMA)结构化
        "ms": round(ms, 1),
    }
    _LOG.append(entry)
    _persist(entry)
    try:
        peer_key = "server" if kind == "service_call" else "world"
        session_log.record(kind, {peer_key: world, "method": method, "summary": summary,
                                  "resp": resp or {}, "ms": round(ms, 1)})
    except Exception:
        pass  # 统一日志落盘失败绝不能影响主流程


def recent(after: int = 0) -> list[dict]:
    return [e for e in list(_LOG) if e["id"] > after]


def stats() -> dict:
    by_method: dict[str, int] = {}
    by_world: dict[str, int] = {}
    for e in _LOG:
        by_method[e["method"]] = by_method.get(e["method"], 0) + 1
        by_world[e["world"]] = by_world.get(e["world"], 0) + 1
    return {"total": _SEQ, "by_method": by_method, "by_world": by_world}
