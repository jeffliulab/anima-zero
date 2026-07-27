"""ANIMA 棋类引擎 —— 独立 **MCP service**（棋理顾问），多棋种在此分流。

大脑一个 host 同时连 world server（棋盘现实）+ 这个 service（棋理），就是 MCP 的多 server 用法。
挂载由 **Host（ANIMA）按 `config.services()` 组装**——server 之间互不相识（标准 MCP 模型）；
本服务不认识任何 world，可与 sim-chess / gazebo-chess / 未来实机自由配对，跟着大脑跨身体走。
engine 纯计算、不碰物理、不持有对局（每次给 FEN）。**棋规合法性（legal_moves）也在这层**——绝不放
world（world 只是棋盘现实）。它是大脑的高层「想棋」帮手，不是实时控制——真机实时控制永不走 MCP。

- 工具（当前只接国际象棋）：`best_move(fen)` / `evaluate(fen)` / `legal_moves(fen)`。FEN 由大脑
  自己看图+读对局历史推出来；FEN 不合法 → 工具报可读错误（大脑据此自我修正后重试），不静默兜底。
- go_engine / gomoku_engine 已就位、暂不暴露工具（无消费方 + 局面输入格式未定，见 README.md）。
- 起（在 anima-zero 根，用 anima venv）：
    ./.venv/bin/uvicorn services.boardgame_engine.app:app --host 127.0.0.1 --port 8108
- 可调项走**本服务自带 env**（服务独立进程，不 import 脑 config；默认值在此一处）：
  `ANIMA_ENGINE_DEPTH`、`ANIMA_ENGINE_TIME`。
"""
from __future__ import annotations

import os

# anima-chess: this repository's own MIT rules library. Its public API mirrors the
# subset of python-chess this file used, so the alias leaves every call below untouched.
# anima-chess：本仓自带的 MIT 规则库。公开 API 与本文件原先用到的那部分 python-chess 一致，
# 起个别名就够了，下面的调用一行都不用改。
import anima_chess as chess
from mcp.server.fastmcp import FastMCP

from . import chess_engine

# 就位待接的棋种引擎（无消费方，暂不实例化、不暴露工具；接入条件见 README.md）：
# from . import go_engine
# from . import gomoku_engine

# 可调项（本服务自带 env，默认集中在此；不 import 脑 config——服务是独立进程/独立模块）
_ENGINE_DEPTH = int(os.getenv("ANIMA_ENGINE_DEPTH", "3"))
_ENGINE_TIME = float(os.getenv("ANIMA_ENGINE_TIME", "1.5"))

_ai = chess_engine.AI(depth=_ENGINE_DEPTH, time_limit=_ENGINE_TIME)

mcp = FastMCP("anima-boardgame-engine")


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
    return int(chess_engine.evaluate(_board(fen)))


@mcp.tool()
def legal_moves(fen: str) -> list[str]:
    """给一个 FEN，返回全部合法着法（UCI 列表）——棋规合法性在引擎/大脑侧，绝不放 world。"""
    return [m.uci() for m in _board(fen).legal_moves]


app = mcp.streamable_http_app()   # 用 uvicorn 跑；MCP 挂在 /mcp
