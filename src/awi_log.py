"""AWI 流量记账(ANIMA 端):记录每一次脑↔世界的调用,给 /awi 仪表盘的实时 terminal + 统计用。

这是把「AWI 这套接口」可视化:谁(哪个世界)被调了什么(capabilities / perceive / invoke)、耗时多少。
"""
from __future__ import annotations

import json
import os
import time
from collections import deque

# 脑端保留多少条 AWI 流量历史。世界端(world/sim-desk)有自己的同名常量,数值需对齐;
# 前端 terminal 显示数(AWI_LOG_SHOWN)必须 ≤ 这个值,否则永远凑不满。
AWI_LOG_MAXLEN = 400
_LOG: deque = deque(maxlen=AWI_LOG_MAXLEN)
_SEQ = 0

# 除了内存(给 /awi 仪表盘实时看),每条流量也落到本地文件,方便追溯历史。
# 一天一个文件:logs/awi-YYYY-MM-DD.jsonl,每行一条 JSON。logs/ 已在 .gitignore,不入库、不 push。
_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")


def _persist(entry: dict) -> None:
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        path = os.path.join(_LOG_DIR, "awi-" + time.strftime("%Y-%m-%d") + ".jsonl")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # 落盘失败绝不能影响主流程


def record(world: str, method: str, summary: str, ms: float) -> None:
    global _SEQ
    _SEQ += 1
    entry = {
        "id": _SEQ,
        "ts": time.strftime("%H:%M:%S"),
        "world": world,
        "method": method,
        "summary": summary,
        "ms": round(ms, 1),
    }
    _LOG.append(entry)
    _persist(entry)


def recent(after: int = 0) -> list[dict]:
    return [e for e in list(_LOG) if e["id"] > after]


def stats() -> dict:
    by_method: dict[str, int] = {}
    by_world: dict[str, int] = {}
    for e in _LOG:
        by_method[e["method"]] = by_method.get(e["method"], 0) + 1
        by_world[e["world"]] = by_world.get(e["world"], 0) + 1
    return {"total": _SEQ, "by_method": by_method, "by_world": by_world}
