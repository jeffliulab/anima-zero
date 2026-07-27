"""anima-chess — chess rules for ANIMA: legal moves, check, checkmate, draws.

This is a **rules** library, not an engine. It answers "which moves are legal here?" and
"is this game over?". Deciding *which* legal move is a good one lives elsewhere — in
ANIMA's board-game engine service, which was written independently and is untouched by
this package.

## Why it exists

ANIMA used `python-chess`, which is excellent and is licensed GPL-3.0. That made the whole
repository's licence a question rather than a statement. Everything else ANIMA depends on
— all 69 backend packages, the 46 in the navigation world, the robot models, the scene
assets — is permissive. This library replaces the one exception so the project can be MIT
throughout.

The public names deliberately match the subset of `python-chess` that ANIMA actually used
(measured: 28 names), so the call sites changed one import line and nothing else.

## What it does not do

Chess960, PGN reading or writing, opening books, UCI engine communication, SAN parsing.
None of it was used, so none of it is here. If you need those, use `python-chess` — it is
a better library and this one does not try to compete with it.

anima-chess —— 给 ANIMA 用的国际象棋规则：合法走法、将军、将死、和棋。

这是一个**规则**库，不是引擎。它回答"这里能走哪些"和"这盘棋结束了吗"。至于合法走法里**哪一步好**，
那是别处的事——住在 ANIMA 的棋类引擎 service 里，那套搜索算法是独立写的，本包一个字都没碰它。

## 为什么有这个包

ANIMA 原来用 `python-chess`——一个非常好的库，许可证是 GPL-3.0。这让整个仓库的许可证成了一个
"需要解释的问题"而不是"一句话就说清的事实"。ANIMA 依赖的其它一切——后端 69 个包、导航世界的 46 个包、
机器人模型、场景资产——**全是宽松协议**。这个库替掉唯一的例外，好让整个项目从头到尾都是 MIT。

公开的名字**刻意**与 ANIMA 实际用到的那部分 `python-chess` API 保持一致（实测 28 个名字），
所以调用点只改了一行 import、别的一行没动。

## 它不做的事

Chess960、PGN 读写、开局库、UCI 引擎通信、SAN 记谱解析。这些原本就没被用到，所以这里也没有。
真需要那些，请用 `python-chess`——它是更好的库，这个包不打算跟它比。
"""
from ._attacks import (
    BB_KING_ATTACKS, BB_KNIGHT_ATTACKS, BB_PAWN_ATTACKS,
    bishop_attacks, queen_attacks, rook_attacks,
)
from ._board import STARTING_FEN, Board, Status
from ._types import (
    BB_ALL, BB_EMPTY, BB_FILES, BB_RANKS, BB_SQUARES, BISHOP, BLACK, COLORS, KING, KNIGHT,
    PAWN, PIECE_SYMBOLS, PIECE_TYPES, QUEEN, ROOK, SQUARE_NAMES, SQUARES, WHITE,
    Move, Piece, lsb, msb, parse_square, popcount, scan_forward, square, square_file,
    square_name, square_rank,
)
from ._version import __version__

__all__ = [
    "__version__",
    # colours / 颜色
    "WHITE", "BLACK", "COLORS",
    # piece types / 棋子类型
    "PAWN", "KNIGHT", "BISHOP", "ROOK", "QUEEN", "KING", "PIECE_TYPES", "PIECE_SYMBOLS",
    # squares / 格子
    "SQUARES", "SQUARE_NAMES", "square", "square_file", "square_rank", "square_name",
    "parse_square",
    # bitboards / 位棋盘
    "BB_ALL", "BB_EMPTY", "BB_SQUARES", "BB_FILES", "BB_RANKS",
    "BB_KNIGHT_ATTACKS", "BB_KING_ATTACKS", "BB_PAWN_ATTACKS",
    "bishop_attacks", "rook_attacks", "queen_attacks",
    "msb", "lsb", "popcount", "scan_forward",
    # the game / 对局
    "Board", "Move", "Piece", "Status", "STARTING_FEN",
]
