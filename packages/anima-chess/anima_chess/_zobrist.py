"""Zobrist hashing — giving every position a 64-bit name.

The idea: assign one random 64-bit number to every (piece, colour, square) combination,
plus a few for side-to-move, castling rights and the en-passant file. A position's key is
all of its numbers XOR-ed together. Two different positions collide only by accident at
roughly 1 in 2^64, and XOR is its own inverse, so a key can be updated by a move rather
than recomputed from scratch.

**Why this library needs it right now**: the draw-by-repetition rules ("the same position
three times") require deciding whether two positions are the same, and comparing whole
boards is far too slow to do at every node. A single integer key makes it a dict lookup.
Transposition tables — the classic first upgrade to a search engine — want exactly the
same key, which is why it is worth building properly the first time.

Zobrist 哈希 —— 给每个局面起一个 64 位的名字。

思路：给「棋子 × 颜色 × 格子」的每一种组合分配一个随机 64 位数，再给"轮到谁走""易位权""吃过路兵
所在列"各配几个。一个局面的键 = 它拥有的所有数字异或起来。两个不同局面撞名的概率约为 1/2^64；
而异或的逆运算是它自己，所以走一步棋可以**增量更新**这个键，不必从头算。

**为什么现在就需要它**：判和棋的重复局面规则（"同一局面出现三次"）要求判断两个局面是不是同一个，
而在每个节点上比较整张棋盘太慢了。换成一个整数键，就变成一次字典查找。而置换表——搜索引擎最经典的
第一项升级——要的正是同一个键，所以第一次就把它做对是划算的。
"""
from __future__ import annotations

import random

from ._types import COLORS, SQUARES

# A fixed seed, not `random.seed()` from the clock.
#
# The keys must be identical every run: a position saved today has to hash the same
# tomorrow, and two processes (the engine service and the world) must agree. Deriving them
# from one documented seed keeps that guarantee while avoiding a wall of magic constants
# in the source. (This is not cryptography — a plain PRNG is exactly right here.)
#
# 用固定种子，不是按时钟 `random.seed()`。
#
# 这些键每次运行都必须一模一样：今天存下的局面明天要哈希出同一个值，而两个进程（引擎 service 和
# 世界）也必须算得一致。从一个**写明出处的种子**推导出来，既保证了这一点，又不用在源码里堆一大片
# 魔法常数。（这不是密码学，普通伪随机数在这里正合适。）
_SEED = 0x616E696D615F636B  # "anima_ck" in ASCII / ASCII 里的 "anima_ck"


def _build_tables():
    """Everything is drawn inside one function so the generator stays local and cannot be
    reused — the tables must be built exactly once, in this order, or the numbers change.
    / 全部在一个函数里抽取，好让随机数发生器留在局部、无法被再次使用——这些表必须**恰好按这个顺序、
    只建一次**，否则数字就变了。"""
    rng = random.Random(_SEED)

    def key() -> int:
        return rng.getrandbits(64)

    # [colour][piece_type][square]; colour is a bool so it indexes as 0/1, and piece types
    # start at 1 so slot 0 stays unused (cheaper than subtracting one everywhere).
    # [颜色][棋子类型][格子]；颜色是 bool，直接当 0/1 用；棋子类型从 1 开始，0 号槽空着不用
    # （比到处写"减一"更省事）。
    piece_keys = [[[key() for _ in SQUARES] for _ in range(7)] for _ in COLORS]
    # XOR-ed in whenever it is Black to move. / 轮到黑走时异或进来。
    turn_key = key()
    # One per castling right, indexed by the rook's home square (A1, H1, A8, H8).
    # 每项易位权一个，按车的原始格子索引（A1、H1、A8、H8）。
    castling_keys = {sq: key() for sq in (0, 7, 56, 63)}
    # One per file. Only mixed in when an en-passant capture is actually available — see
    # the note in `_board.py`. / 每列一个。只有**真的能吃过路兵**时才混进去，原因见 `_board.py`。
    ep_file_keys = [key() for _ in range(8)]
    return piece_keys, turn_key, castling_keys, ep_file_keys


PIECE_KEYS, TURN_KEY, CASTLING_KEYS, EP_FILE_KEYS = _build_tables()
