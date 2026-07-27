"""Precomputed attack tables — the reason this library is fast enough to search with.

The whole problem: "which squares does a rook on d4 attack?" depends on which pieces are
in the way, so it cannot be a single fixed table. Walking outwards at query time is the
obvious answer and it is what makes a naive engine slow — a search asks this question
millions of times.

The fix is to do the walking **once, at import time, for every position a blocker could
possibly be in**, and store the answers. At query time it becomes a dictionary lookup.

Two details make the table small enough to be practical:

1. **Only squares between the piece and the board edge matter.** Whatever sits on the
   edge square itself cannot block anything further — there is nothing further. So the
   edges are excluded from the "relevant" mask, which halves the number of bits.
2. **Rook attacks are split into rank and file.** A rook's relevant mask is up to 12 bits
   (4096 combinations); splitting it into two 6-bit masks gives 64 + 64 instead.

预计算攻击表 —— 这个库能快到可以拿来做搜索，全靠它。

问题是这样的：「d4 的车攻击哪些格子」取决于路上有没有别的子挡着，所以它不可能是一张固定的表。
最直观的做法是查询时从车的位置往外走一遍——而这正是朴素引擎慢的原因：一次搜索要问这个问题几百万次。

解法是**在 import 时把"阻挡子可能在的每一种摆法"都走一遍**，把答案全存下来。查询时就退化成一次字典查找。

有两个细节让这张表小到实用：

1. **只有"子与棋盘边缘之间"的格子才有意义。** 边缘格上摆什么都挡不住更远的东西——它后面已经没有
   东西了。所以把边缘排除在"相关掩码"之外，位数直接减半。
2. **车的攻击拆成横行和竖列两张表。** 车的相关掩码最多 12 位（4096 种组合）；拆成两张 6 位的表，
   就变成 64 + 64 种。
"""
from __future__ import annotations

from ._types import (
    BB_ALL, BB_EMPTY, BB_FILES, BB_RANKS, BB_SQUARES, SQUARES,
    square_file, square_rank,
)

# Directions as square-number offsets. +8 is "one rank up", +1 is "one file right".
# 方向用「格子编号的增量」表示。+8 = 往上一行，+1 = 往右一列。
_DIAG_DELTAS = [-9, -7, 7, 9]
_FILE_DELTAS = [-8, 8]
_RANK_DELTAS = [-1, 1]
_KNIGHT_DELTAS = [17, 15, 10, 6, -17, -15, -10, -6]
_KING_DELTAS = [9, 8, 7, 1, -9, -8, -7, -1]
_WHITE_PAWN_DELTAS = [7, 9]
_BLACK_PAWN_DELTAS = [-7, -9]


def _sliding_attacks(square: int, occupied: int, deltas: list[int]) -> int:
    """Walk outwards from `square` in each direction until the board edge or a piece.

    The blocker square itself **is** included — a rook attacks the pawn that blocks it,
    it just cannot see past it.

    The wrap-around guard is the subtle part: square numbers are a flat 0..63 list, so
    stepping right from h4 (39) lands on a5 (40), which looks fine numerically but is
    nonsense on a board. Checking that the file moved by at most 2 catches every such
    wrap, for sliding directions and knight jumps alike.

    从 `square` 出发沿每个方向往外走，撞到棋盘边缘或撞到子为止。

    **挡路的那个格子本身算在内**——车攻击那个挡住它的兵，只是看不到更远。

    绕行判断是这里最微妙的一点：格子编号是 0..63 的一维排列，所以从 h4(39) 往右走一步会落到
    a5(40)，数值上看没问题，放在棋盘上却是荒唐的。检查"列最多只移动 2"就能抓住所有这类绕行——
    对滑行方向和马的跳跃都成立。
    """
    attacks = BB_EMPTY
    for delta in deltas:
        sq = square
        while True:
            prev = sq
            sq += delta
            if not (0 <= sq < 64) or abs(square_file(sq) - square_file(prev)) > 2:
                break
            attacks |= BB_SQUARES[sq]
            if occupied & BB_SQUARES[sq]:
                break
    return attacks


def _step_attacks(square: int, deltas: list[int]) -> int:
    """One step in each direction. Implemented as "sliding on a completely full board",
    which stops after exactly one square. / 每个方向只走一步。做法是「在一个塞满子的棋盘上滑行」
    ——那样正好走一格就停。"""
    return _sliding_attacks(square, BB_ALL, deltas)


BB_KNIGHT_ATTACKS = [_step_attacks(sq, _KNIGHT_DELTAS) for sq in SQUARES]
BB_KING_ATTACKS = [_step_attacks(sq, _KING_DELTAS) for sq in SQUARES]
# Indexed by colour, and colour is a bool, so [BLACK] is [0] and [WHITE] is [1].
# 按颜色索引；颜色是 bool，所以 [BLACK] 就是 [0]、[WHITE] 就是 [1]。
BB_PAWN_ATTACKS = [
    [_step_attacks(sq, _BLACK_PAWN_DELTAS) for sq in SQUARES],
    [_step_attacks(sq, _WHITE_PAWN_DELTAS) for sq in SQUARES],
]


def _edges(square: int) -> int:
    """The border squares that are irrelevant to this square's sliding attacks: the first
    and last rank (unless the piece is already on it) plus the a- and h-files (same).
    / 对这个格子的滑行攻击来说无关紧要的边缘格：第 1、8 横线（除非子本来就在上面）
    加上 a、h 两条竖线（同理）。"""
    return (((BB_RANKS[0] | BB_RANKS[7]) & ~BB_RANKS[square_rank(square)])
            | ((BB_FILES[0] | BB_FILES[7]) & ~BB_FILES[square_file(square)]))


def _carry_rippler(mask: int):
    """Enumerate every subset of the set bits in `mask`, including 0 and `mask` itself.

    `subset = (subset - mask) & mask` is a well-known trick: subtracting borrows through
    exactly the bits of the mask, so repeated application walks all 2^n subsets in order
    and returns to 0 at the end.

    枚举 `mask` 里被置位那些位的**每一个子集**，含空集和全集。

    `subset = (subset - mask) & mask` 是个著名技巧：减法的借位恰好在掩码的那些位之间传递，
    所以反复施加它就能依次走遍全部 2^n 个子集，最后回到 0。
    """
    subset = 0
    while True:
        yield subset
        subset = (subset - mask) & mask
        if not subset:
            return


def _attack_table(deltas: list[int]) -> tuple[list[int], list[dict[int, int]]]:
    """Build (relevant-mask per square, {occupancy -> attacks} per square).
    / 为每个格子建出（相关掩码，{占位 -> 攻击} 字典）。"""
    masks: list[int] = []
    tables: list[dict[int, int]] = []
    for sq in SQUARES:
        table: dict[int, int] = {}
        mask = _sliding_attacks(sq, 0, deltas) & ~_edges(sq)
        for subset in _carry_rippler(mask):
            table[subset] = _sliding_attacks(sq, subset, deltas)
        masks.append(mask)
        tables.append(table)
    return masks, tables


BB_DIAG_MASKS, BB_DIAG_ATTACKS = _attack_table(_DIAG_DELTAS)
BB_FILE_MASKS, BB_FILE_ATTACKS = _attack_table(_FILE_DELTAS)
BB_RANK_MASKS, BB_RANK_ATTACKS = _attack_table(_RANK_DELTAS)


def bishop_attacks(square: int, occupied: int) -> int:
    """/ 象在给定占位下的攻击范围。"""
    return BB_DIAG_ATTACKS[square][BB_DIAG_MASKS[square] & occupied]


def rook_attacks(square: int, occupied: int) -> int:
    """/ 车：横行与竖列两张表的并集。"""
    return (BB_RANK_ATTACKS[square][BB_RANK_MASKS[square] & occupied]
            | BB_FILE_ATTACKS[square][BB_FILE_MASKS[square] & occupied])


def queen_attacks(square: int, occupied: int) -> int:
    """/ 后 = 车 + 象。"""
    return rook_attacks(square, occupied) | bishop_attacks(square, occupied)


# --- Between / ray tables --------------------------------------------------------------
# BB_RAYS[a][b]  = every square on the infinite line through a and b (empty if not aligned)
# BB_BETWEEN[a][b] = the squares strictly between a and b (empty if not aligned)
#
# These two answer the questions that pin detection and check evasion are made of:
# "is my king on the same line as that rook?" and "which squares could I interpose on?"
#
# BB_RAYS[a][b]    = 穿过 a 和 b 的整条直线上的所有格（不共线则为空）
# BB_BETWEEN[a][b] = **严格夹在** a 和 b 之间的格（不共线则为空）
#
# 这两张表回答的正是"牵制判定"和"应将"要问的问题：
# 「我的王和那个车在同一条线上吗」以及「我能垫在哪些格子上」。
BB_RAYS: list[list[int]] = []
BB_BETWEEN: list[list[int]] = []
for a in SQUARES:
    rays_a, between_a = [], []
    bb_a = BB_SQUARES[a]
    for b in SQUARES:
        bb_b = BB_SQUARES[b]
        if BB_DIAG_ATTACKS[a][0] & bb_b:
            ray = (BB_DIAG_ATTACKS[a][0] & BB_DIAG_ATTACKS[b][0]) | bb_a | bb_b
            between = BB_DIAG_ATTACKS[a][BB_DIAG_MASKS[a] & bb_b] & \
                BB_DIAG_ATTACKS[b][BB_DIAG_MASKS[b] & bb_a]
        elif BB_RANK_ATTACKS[a][0] & bb_b:
            ray = BB_RANK_ATTACKS[a][0] | bb_a
            between = BB_RANK_ATTACKS[a][BB_RANK_MASKS[a] & bb_b] & \
                BB_RANK_ATTACKS[b][BB_RANK_MASKS[b] & bb_a]
        elif BB_FILE_ATTACKS[a][0] & bb_b:
            ray = BB_FILE_ATTACKS[a][0] | bb_a
            between = BB_FILE_ATTACKS[a][BB_FILE_MASKS[a] & bb_b] & \
                BB_FILE_ATTACKS[b][BB_FILE_MASKS[b] & bb_a]
        else:
            ray = between = BB_EMPTY
        rays_a.append(ray)
        between_a.append(between)
    BB_RAYS.append(rays_a)
    BB_BETWEEN.append(between_a)
del a, b, bb_a, bb_b, rays_a, between_a, ray, between
