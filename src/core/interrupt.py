"""会话级「叫停」旗标 —— 用户在网页点停止时置位，主循环下一个检查点收尾。

**为什么是进程内内存、不写进会话文件**：这个旗标描述的是「有一轮正在跑、用户想让它停」，
是**运行态**不是记忆。后端一重启，本来就没有任何一轮在跑；若把它持久化，重启后的第一轮
会凭空被叫停——那才是错的。会话的真相（说过什么、核心任务）照旧全在会话文件里。

**语义**：置位是一次性的意向，由主循环消费——收尾时清除，所以一次点击只停一轮，
不会殃及用户接着说的下一句。每轮开始也清一次，兜住「点了停止但那轮已经自己结束了」的竞态。
"""
from __future__ import annotations

import threading

_lock = threading.Lock()
_requested: set[str] = set()


def request(session_id: str) -> None:
    """请求叫停某个会话正在跑的这一轮（网页「停止」按钮 → /interrupt 端点调这里）。"""
    with _lock:
        _requested.add(session_id)


def is_set(session_id: str) -> bool:
    """这一轮是否被要求停下（主循环的检查点、以及动作等待期的 _should_abort 都问它）。"""
    with _lock:
        return session_id in _requested


def clear(session_id: str) -> None:
    """清除旗标（每轮开始时清一次防竞态；收尾时清一次表示这次叫停已被消费）。"""
    with _lock:
        _requested.discard(session_id)
