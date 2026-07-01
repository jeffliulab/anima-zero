"""下棋引擎双路（v0.4 Part B）：配了 ANIMA_ENGINE_URL → 走独立引擎 MCP server（棋理顾问，多 server 用法）；
没配 → 进程内加载引擎（默认）。这里只钉"选路"结构（真正经 MCP 求最优着由端到端冒烟验证，需起引擎 server）。"""
from __future__ import annotations

from anima.tools.boardgame.chess import ChessAdapter


def test_engine_url_selects_mcp_mode(monkeypatch):
    monkeypatch.setenv("ANIMA_ENGINE_URL", "http://localhost:9999")
    a = ChessAdapter()
    assert a._engine_url == "http://localhost:9999" and a.ai is None, \
        "配了 ANIMA_ENGINE_URL → MCP 模式，不加载进程内引擎"


def test_no_env_uses_in_process_engine(monkeypatch):
    monkeypatch.delenv("ANIMA_ENGINE_URL", raising=False)
    a = ChessAdapter()
    assert a._engine_url is None and a.ai is not None, "没配 → 进程内引擎（默认，单测/无额外进程时用）"
