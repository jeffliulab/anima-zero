"""ANIMA 象棋引擎 —— 独立 **MCP service**（棋理顾问）。

大脑一个 host 同时连 world server（棋盘现实）+ 这个 service（棋理），就是 MCP 的多 server 用法。
挂载关系由**棋类 world 自己声明**（capabilities 的 anima://services 资源），大脑握手后自动连接——
本服务与任何 world（sim-chess / gazebo-chess / 未来实机）自由配对，是应用侧的独立模块。
engine 纯计算、不碰物理、不持有对局（每次给 FEN）。**棋规合法性（legal_moves）也在这层**——绝不放
world（world 只是棋盘现实）。

- 工具：`best_move(fen)` / `evaluate(fen)` / `legal_moves(fen)`。FEN 由大脑自己看图+读对局历史推出来；
  FEN 不合法 → 工具报可读错误（大脑据此自我修正后重试），不静默兜底。
- 起（在 anima-zero 根，用 anima venv）：
    ./.venv/bin/uvicorn services.chess_engine_mcp:app --host 127.0.0.1 --port 8108
- 可调项走**本服务自带 env**（服务独立进程，不 import 脑 config；默认值在此一处）：
  `ANIMA_CHESS_ENGINE_PATH`（引擎源码路径，默认从仓库结构派生）、`ANIMA_ENGINE_DEPTH`、`ANIMA_ENGINE_TIME`。
- 复用同一份引擎（`3-anima-chess-engine/chess/engine.py`）——不改引擎源码，只在外面包。
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import chess
from mcp.server.fastmcp import FastMCP

# 可调项（本服务自带 env，默认集中在此；不 import 脑 config——服务是独立进程/独立模块）
_ENGINE_DEPTH = int(os.getenv("ANIMA_ENGINE_DEPTH", "3"))
_ENGINE_TIME = float(os.getenv("ANIMA_ENGINE_TIME", "1.5"))


def _engine_path() -> str:
    """引擎源码路径：默认从仓库结构派生（services/ → 仓库根 → 再上两级到项目根，
    再拼 3-anima-chess-engine/chess/engine.py），env ANIMA_CHESS_ENGINE_PATH 覆盖。"""
    env = os.getenv("ANIMA_CHESS_ENGINE_PATH")
    if env:
        return env
    root = Path(__file__).resolve().parents[3]
    return str(root / "3-anima-chess-engine" / "chess" / "engine.py")


def _load_engine():
    spec = importlib.util.spec_from_file_location("anima_chess_engine", _engine_path())
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_engine = _load_engine()
_ai = _engine.AI(depth=_ENGINE_DEPTH, time_limit=_ENGINE_TIME)

mcp = FastMCP("anima-chess-engine")


def _board(fen: str) -> chess.Board:
    """解析 FEN；不合法就抛**可读错误**（FastMCP 会把异常转成工具错误结果返回给大脑）。
    这是工具的诚实报错、给大脑自我修正的反馈，不是替它决策。"""
    try:
        board = chess.Board(fen)
    except ValueError as e:
        raise ValueError(f"FEN 不合法（{e}）。请重新对照棋盘画面和对局历史，核对每一格后再给一次完整 FEN。")
    if not board.is_valid():
        raise ValueError(f"FEN 局面不成立（{board.status()!r}，如王的数量/位置不对）。"
                         "请重新对照棋盘画面核对后再给。")
    return board


@mcp.tool()
def best_move(fen: str) -> str:
    """国际象棋引擎顾问：给它当前局面的 FEN，返回该局面下轮到方的最佳走法（UCI，如 e7e5；无子可走返回空串）。
    FEN 要你自己从棋盘画面和对局历史推出来（包括轮到谁走、易位权等）；FEN 不合法会报错并说明原因。"""
    mv = _ai.best_move(_board(fen))
    return mv.uci() if mv else ""


@mcp.tool()
def evaluate(fen: str) -> int:
    """给一个 FEN，返回静态评估分（厘兵，正 = 轮到方有利）。FEN 不合法会报错并说明原因。"""
    return int(_engine.evaluate(_board(fen)))


@mcp.tool()
def legal_moves(fen: str) -> list[str]:
    """给一个 FEN，返回全部合法着法（UCI 列表）——棋规合法性在引擎/大脑侧，绝不放 world。"""
    return [m.uci() for m in _board(fen).legal_moves]


app = mcp.streamable_http_app()   # 用 uvicorn 跑；MCP 挂在 /mcp
