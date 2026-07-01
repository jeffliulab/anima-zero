"""ANIMA 象棋引擎 —— 独立 **MCP server**（棋理顾问）。

v0.4 「engine 独立成服务」：大脑一个 host **同时连 world server（棋盘现实）+ 这个 engine server（棋理）**，
就是 MCP 的多 server 用法。engine 纯计算、不碰物理、不持有对局（每次给 FEN）。
**棋规合法性（legal_moves）也在这层**——绝不放 world（world 只是棋盘现实）。

- 工具：`best_move(fen)` / `evaluate(fen)` / `legal_moves(fen)`。
- 起（在 anima-zero 根，用 anima venv）：
    ./.venv/bin/uvicorn services.chess_engine_mcp:app --host 127.0.0.1 --port 8108
  大脑侧配 `ANIMA_ENGINE_URL=http://localhost:8108`，下棋适配器就经 MCP 求最优着（没配则用进程内引擎）。
- 复用同一份引擎（`config.chess_engine_path()`，env ANIMA_CHESS_ENGINE_PATH 可覆盖）——不改引擎源码，只在外面包。
"""
from __future__ import annotations

import importlib.util
import os

import chess
from mcp.server.fastmcp import FastMCP

from anima import config


def _load_engine():
    spec = importlib.util.spec_from_file_location("anima_chess_engine", config.chess_engine_path())
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_engine = _load_engine()
_ai = _engine.AI(depth=int(os.getenv("ANIMA_ENGINE_DEPTH", str(config.CHESS_DEPTH))),
                 time_limit=float(os.getenv("ANIMA_ENGINE_TIME", str(config.CHESS_TIME))))

mcp = FastMCP("anima-chess-engine")


@mcp.tool()
def best_move(fen: str) -> str:
    """给一个 FEN 局面，返回引擎认为的最佳走法（UCI，如 e2e4）；无子可走返回空串。"""
    mv = _ai.best_move(chess.Board(fen))
    return mv.uci() if mv else ""


@mcp.tool()
def evaluate(fen: str) -> int:
    """给一个 FEN，返回静态评估分（厘兵，正 = 轮到方有利）。"""
    return int(_engine.evaluate(chess.Board(fen)))


@mcp.tool()
def legal_moves(fen: str) -> list[str]:
    """给一个 FEN，返回全部合法着法（UCI 列表）——棋规合法性在引擎/大脑侧，绝不放 world。"""
    return [m.uci() for m in chess.Board(fen).legal_moves]


app = mcp.streamable_http_app()   # 用 uvicorn 跑；MCP 挂在 /mcp
