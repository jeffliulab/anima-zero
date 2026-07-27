"""Perft — the acceptance gate for the rules.

Perft walks the full move tree to a given depth and counts the leaves. That single number
is a remarkably sharp test: get castling rights, en passant, promotion, pins or check
evasion wrong by one move in one position, and the count comes out different. "I played a
few games and it looked fine" cannot do that.

The expected values below are the published reference figures for six positions that the
chess programming community has used for decades. They were additionally cross-checked
against `python-chess` while this library was being written, and then frozen here — the
tests carry no dependency on it.

Perft —— 规则的准入门槛。

Perft 把走法树完整走到指定深度，数一数叶子有多少个。这一个数字是极其锐利的检验：易位权、吃过路兵、
升变、牵制、应将——任何一个局面里差一步走法，总数就对不上。"我下了几盘看着没问题"做不到这一点。

下面的期望值是国际象棋编程界用了几十年的六个标准局面的**公开参考值**。开发本库时另外用
`python-chess` 交叉核对过一遍，然后冻结在这里——测试本身不依赖它。
"""
from __future__ import annotations

import os

import pytest

from anima_chess import Board

# (name, fen, {depth: expected leaf count})
# 局面 3 is deliberately lopsided (no castling, no king safety) and catches pawn and
# check-evasion bugs the tidier positions miss.
# 局面 3 有意设计得很偏（没有易位、王也不安全），能抓住那些"漂亮局面"漏掉的兵和应将的 bug。
POSITIONS = [
    (
        "initial / 初始局面",
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        {1: 20, 2: 400, 3: 8_902, 4: 197_281, 5: 4_865_609},
    ),
    (
        "kiwipete",
        "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
        {1: 48, 2: 2_039, 3: 97_862, 4: 4_085_603},
    ),
    (
        "position 3 / 局面 3",
        "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
        {1: 14, 2: 191, 3: 2_812, 4: 43_238, 5: 674_624},
    ),
    (
        "position 4 / 局面 4",
        "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1",
        {1: 6, 2: 264, 3: 9_467, 4: 422_333},
    ),
    (
        "position 5 / 局面 5",
        "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8",
        {1: 44, 2: 1_486, 3: 62_379, 4: 2_103_487},
    ),
    (
        "position 6 / 局面 6",
        "r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10",
        {1: 46, 2: 2_079, 3: 89_890, 4: 3_894_594},
    ),
]

# How deep the default run goes. The deeper layers take minutes, which is too slow to run
# on every push — but they are the ones that catch the rarest bugs, so they stay available
# behind a switch rather than being deleted.
#     ANIMA_CHESS_PERFT_DEPTH=5 pytest      # the full, slow sweep
# 默认跑到第几层。更深的层要几分钟，每次推送都跑太慢——但恰恰是它们能抓住最罕见的 bug，
# 所以用一个开关留着，而不是删掉。
DEFAULT_MAX_DEPTH = 3
MAX_DEPTH = int(os.environ.get("ANIMA_CHESS_PERFT_DEPTH", DEFAULT_MAX_DEPTH))


def perft(board: Board, depth: int) -> int:
    if depth == 0:
        return 1
    total = 0
    for move in board.legal_moves:
        board.push(move)
        total += perft(board, depth - 1)
        board.pop()
    return total


def _cases():
    for name, fen, expected in POSITIONS:
        for depth, nodes in sorted(expected.items()):
            if depth <= MAX_DEPTH:
                yield pytest.param(fen, depth, nodes, id=f"{name}-d{depth}")


@pytest.mark.parametrize("fen,depth,expected", list(_cases()))
def test_perft(fen: str, depth: int, expected: int):
    assert perft(Board(fen), depth) == expected


def test_perft_divide_is_stable():
    """Same position, two different move orders, same leaf count per first move.

    A weaker but much faster check that push/pop leaves nothing behind — if unmaking a move
    failed to restore castling rights or the en-passant square, the second pass would
    disagree with the first.

    同一个局面、两种不同的走法顺序，每个首步下的叶子数应当一致。

    这是一个更弱但快得多的检验，用来确认 push/pop 没有留下残留——如果悔棋没能还原易位权或吃过路兵格，
    第二遍就会和第一遍对不上。
    """
    fen = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"
    board = Board(fen)
    first = {}
    for move in list(board.legal_moves):
        board.push(move)
        first[move.uci()] = perft(board, 2)
        board.pop()

    board = Board(fen)
    second = {}
    for move in reversed(list(board.legal_moves)):
        board.push(move)
        second[move.uci()] = perft(board, 2)
        board.pop()

    assert first == second
    assert board.fen() == fen, "the board must be exactly where it started / 棋盘必须回到原样"
