"""【兼容层，W3 删除】内容已整体并入 `session_log.py`（Session Logs 统一日志，W1）。

这里只 re-export 旧名字，让 server.py / 旧调用方在过渡期零改动可用：
- contextvar 机制与 LoggingLLM → 直接是 session_log 的同一份；
- recent() → 从统一日志里只取 kind=llm_call（旧 /api/anima-logs 的语义）；
- 旧 `logs/anima/` 目录停写、留盘归档，历史要查就翻文件。
"""
from __future__ import annotations

from . import session_log
from .session_log import (  # noqa: F401  （re-export：旧调用方零改动）
    LoggingLLM,
    bind_session,
    bound_stream,
    current_session,
    session_scope,
)


def recent(limit: int = 300, session: str = "") -> list[dict]:
    return session_log.recent(limit, session, kinds=("llm_call",))


def sessions() -> list[str]:
    return session_log.sessions()
