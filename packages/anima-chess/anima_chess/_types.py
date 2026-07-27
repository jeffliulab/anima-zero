"""Squares, colours, piece types, `Piece` and `Move`.

Naming and numbering deliberately mirror `python-chess`, because ANIMA's engine and the
sim-chess world were written against that API. Keeping the names identical means those
files change one import line and nothing else — which is the cheapest possible way to
swap out a dependency without risking a silent behaviour change.

格子、颜色、棋子类型，以及 `Piece` 与 `Move`。

命名和编号**刻意**照抄 `python-chess`，因为 ANIMA 的引擎和 sim-chess 世界当初就是照那套 API 写的。
名字保持一致，那几个文件就只需要改一行 import、别的一行不动——这是替换一个依赖时把"静默改变行为"
的风险压到最低的最省办法。
"""
from __future__ import annotations

# --- Colours ---------------------------------------------------------------------------
# White is `True` and black is `False`, same as python-chess. Two reasons this is not as
# odd as it looks: flipping side is just `not colour`, and a colour doubles as an index
# into a two-element list (`False` == 0, `True` == 1).
# 白 = True、黑 = False，与 python-chess 一致。看着怪，其实有两个好处：换边就是 `not colour`；
# 而颜色本身又能直接当作二元列表的下标（False 就是 0，True 就是 1）。
WHITE = True
BLACK = False
COLORS = [WHITE, BLACK]

# --- Piece types -----------------------------------------------------------------------
# 1..6 so that 0 can mean "no piece" and so they index straight into small tables.
# 用 1..6，好让 0 表示「没有子」，并且能直接给小表当下标。
PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING = range(1, 7)
PIECE_TYPES = [PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING]
PIECE_SYMBOLS = [None, "p", "n", "b", "r", "q", "k"]

# --- Squares ---------------------------------------------------------------------------
# a1 = 0, b1 = 1, ... h8 = 63. Rank-major, starting from White's home rank.
#
# ⛔ This numbering is NOT free to change. ANIMA's engine indexes its piece-square tables
# by square number and mirrors them for Black with `square ^ 56`. That trick only works
# because ranks are 8 apart and rank 1 comes first. Renumber the board and the engine
# silently scores every position wrong — no crash, just worse chess.
#
# a1 = 0、b1 = 1 …… h8 = 63。按横行排列，从白方底线开始数。
#
# ⛔ 这个编号**不能随便改**。ANIMA 的引擎用格子编号去查子力位置表，并用 `square ^ 56` 给黑方做上下
# 镜像——这个技巧成立的前提就是「每行差 8、第 1 行在最前」。改了编号，引擎会**静默**把每个局面都
# 算错分：不报错、不崩溃，只是棋越下越烂。
SQUARES = list(range(64))
SQUARE_NAMES = [f + r for r in "12345678" for f in "abcdefgh"]

BB_EMPTY = 0
BB_ALL = (1 << 64) - 1
BB_SQUARES = [1 << sq for sq in SQUARES]

BB_FILES = [sum(BB_SQUARES[sq] for sq in SQUARES if sq & 7 == f) for f in range(8)]
BB_RANKS = [sum(BB_SQUARES[sq] for sq in SQUARES if sq >> 3 == r) for r in range(8)]


def square_file(square: int) -> int:
    """Column, 0 = a-file. / 列，0 是 a 线。"""
    return square & 7


def square_rank(square: int) -> int:
    """Row, 0 = rank 1. / 行，0 是第 1 横线。"""
    return square >> 3


def square(file_index: int, rank_index: int) -> int:
    """Build a square from column and row. / 由列和行拼出格子编号。"""
    return rank_index * 8 + file_index


def square_name(square: int) -> str:
    """0 -> "a1". / 0 变成 "a1"。"""
    return SQUARE_NAMES[square]


def parse_square(name: str) -> int:
    """"e4" -> 28. Raises ValueError on anything else, like python-chess does.
    / "e4" 变成 28。其它输入抛 ValueError，与 python-chess 行为一致。"""
    try:
        return SQUARE_NAMES.index(name)
    except ValueError:
        raise ValueError(f"invalid square name: {name!r}") from None


def msb(bb: int) -> int:
    """Index of the highest set bit. / 最高位的下标。"""
    return bb.bit_length() - 1


def lsb(bb: int) -> int:
    """Index of the lowest set bit. `bb & -bb` isolates it; `bit_length` reads its position.
    / 最低位的下标。`bb & -bb` 把它单独抠出来，再用 `bit_length` 读它在第几位。"""
    return (bb & -bb).bit_length() - 1


def scan_forward(bb: int):
    """Yield set-bit indices, lowest first. / 从低到高逐个吐出被置位的下标。"""
    while bb:
        low = bb & -bb
        yield low.bit_length() - 1
        bb ^= low


def popcount(bb: int) -> int:
    """How many bits are set. / 有几个位被置起来。"""
    return bin(bb).count("1")


class Piece:
    """A piece type plus a colour. Immutable and cheap; there is one per occupied square
    only when someone asks for it — the board itself stores bitboards, not objects.

    棋子类型 + 颜色。轻量、不可变；只有别人来问的时候才会为某个格子造一个——棋盘内部存的是位棋盘，
    不是对象。"""

    __slots__ = ("piece_type", "color")

    def __init__(self, piece_type: int, color: bool):
        self.piece_type = piece_type
        self.color = color

    def symbol(self) -> str:
        """Uppercase for White, lowercase for Black — FEN's convention.
        / 白大写、黑小写，就是 FEN 的写法。"""
        s = PIECE_SYMBOLS[self.piece_type]
        return s.upper() if self.color else s

    @classmethod
    def from_symbol(cls, symbol: str) -> "Piece":
        return cls(PIECE_SYMBOLS.index(symbol.lower()), symbol.isupper())

    def __eq__(self, other) -> bool:
        return (isinstance(other, Piece) and other.piece_type == self.piece_type
                and other.color == self.color)

    def __hash__(self) -> int:
        return self.piece_type * 2 + int(self.color)

    def __repr__(self) -> str:
        return f"Piece.from_symbol({self.symbol()!r})"

    def __str__(self) -> str:
        return self.symbol()


class Move:
    """Where a piece came from, where it went, and what a pawn turned into.

    Note what is *not* here: whether it was a capture, whether it gave check, whether it
    was castling. A move on its own cannot know any of that — it only means something
    relative to a position. Asking `board.is_capture(move)` rather than `move.is_capture()`
    keeps that honest.

    子从哪来、到哪去、兵变成了什么。

    注意这里**没有**的东西：是不是吃子、有没有将军、是不是易位。一步棋自己无从知道这些——它只有
    放在某个局面里才有意义。所以是问 `board.is_capture(move)` 而不是 `move.is_capture()`，
    这样才不会自欺。"""

    __slots__ = ("from_square", "to_square", "promotion")

    def __init__(self, from_square: int, to_square: int, promotion: int | None = None):
        self.from_square = from_square
        self.to_square = to_square
        self.promotion = promotion

    def uci(self) -> str:
        """"e2e4", or "e7e8q" when a pawn promotes. / "e2e4"；升变时是 "e7e8q"。"""
        s = SQUARE_NAMES[self.from_square] + SQUARE_NAMES[self.to_square]
        return s + PIECE_SYMBOLS[self.promotion] if self.promotion else s

    @classmethod
    def from_uci(cls, uci: str) -> "Move":
        if len(uci) not in (4, 5):
            raise ValueError(f"invalid uci: {uci!r}")
        promotion = PIECE_SYMBOLS.index(uci[4]) if len(uci) == 5 else None
        return cls(parse_square(uci[0:2]), parse_square(uci[2:4]), promotion)

    def __bool__(self) -> bool:
        return bool(self.from_square or self.to_square or self.promotion)

    def __eq__(self, other) -> bool:
        return (isinstance(other, Move) and other.from_square == self.from_square
                and other.to_square == self.to_square and other.promotion == self.promotion)

    def __hash__(self) -> int:
        return self.from_square | (self.to_square << 6) | ((self.promotion or 0) << 12)

    def __repr__(self) -> str:
        return f"Move.from_uci({self.uci()!r})"

    def __str__(self) -> str:
        return self.uci()
