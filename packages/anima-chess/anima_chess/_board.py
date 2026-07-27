"""The board: position, move generation, and the rules that end a game.

## How a position is stored

Not as an 8x8 grid of objects. Instead there are six integers — one per piece type — where
bit *i* is set when a piece of that type stands on square *i*. Plus two more for "all White
pieces" and "all Black pieces". A whole position is nine integers.

The payoff is that questions which would be loops become single instructions. "Which of my
pieces can move to e4?" is an AND. "Are any of my pawns on the seventh rank?" is an AND.
Move generation, which a search runs millions of times, is mostly this.

## Why legality is not tested by trying the move

The naive way to find legal moves is: generate everything that looks plausible, play each
one, and see whether your king is now attacked. That is correct and it is what a slow
library does. It costs a make-and-unmake plus a full attack scan **per candidate move**.

The fast way asks the question in reverse, once per position instead of once per move:

* **Which of my pieces are pinned?** Look outwards from my own king along every line. If
  exactly one piece stands between my king and an enemy slider, that piece is pinned — it
  may only move along that same line. One scan finds all of them.
* **Am I in check, and by what?** If yes, most moves are irrelevant: I must move the king,
  capture the checker, or block the line. Generating only those is far cheaper than
  generating everything and throwing most of it away.

After that, a move is legal if the piece is not pinned (or stays on its pin line) — no
trial move needed. Only king moves and en-passant captures still need special care.

棋盘：局面表示、走子生成，以及判定终局的规则。

## 局面是怎么存的

不是 8×8 的对象网格。而是六个整数——每种棋子一个——第 *i* 位被置起来表示第 *i* 格上站着这种子；
再加两个整数表示"白方全部子""黑方全部子"。**一整个局面就是九个整数。**

好处是：本来要写循环的问题变成了一条指令。「我哪些子能走到 e4」是一次按位与。「我有兵在第七行吗」
也是一次按位与。而搜索要跑几百万次的走子生成，主要就是这些操作。

## 为什么判合法性不靠"试着走一步"

找合法走法最直观的办法是：先生成所有看起来能走的，逐个走一遍，看自己的王是不是被将了。这做法是对的，
慢的库就是这么干的。代价是**每个候选走法**都要走一步、再悔一步，外加一次完整的攻击扫描。

快的办法把问题反过来问，从"每步问一次"变成"每个局面问一次"：

* **我哪些子被牵制住了？** 从自己的王沿每条线往外看。如果王和对方某个滑行子（车/象/后）之间**恰好只
  隔着一个子**，那个子就是被牵制的——它只能沿着同一条线动。一次扫描找出全部。
* **我被将了吗？被谁将的？** 如果被将，绝大多数走法根本不用考虑：我只能动王、吃掉将军的子、或者垫在
  中间。只生成这些，比"全生成再扔掉大部分"便宜得多。

有了这两样，一步棋合法的条件就是「这个子没被牵制，或者它仍走在牵制线上」——**不需要真的试走**。
只有王的走法和吃过路兵还需要单独照顾。
"""
from __future__ import annotations

from ._attacks import (
    BB_BETWEEN, BB_KING_ATTACKS, BB_KNIGHT_ATTACKS, BB_PAWN_ATTACKS, BB_RAYS,
    bishop_attacks, queen_attacks, rook_attacks,
)
from ._types import (
    BB_ALL, BB_EMPTY, BB_RANKS, BB_SQUARES, BISHOP, BLACK, COLORS, KING, KNIGHT,
    PAWN, PIECE_SYMBOLS, QUEEN, ROOK, SQUARE_NAMES, WHITE, Move, Piece,
    msb, popcount, scan_forward, square_file, square_rank,
)
from ._zobrist import CASTLING_KEYS, EP_FILE_KEYS, PIECE_KEYS, TURN_KEY

STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

A1, C1, D1, E1, F1, G1, H1 = 0, 2, 3, 4, 5, 6, 7
A8, C8, D8, E8, F8, G8, H8 = 56, 58, 59, 60, 61, 62, 63

BB_CORNERS = BB_SQUARES[A1] | BB_SQUARES[H1] | BB_SQUARES[A8] | BB_SQUARES[H8]
BB_BACKRANKS = BB_RANKS[0] | BB_RANKS[7]
# Colouring of the squares, needed only for the "two bishops on the same colour cannot
# mate" rule. / 格子的黑白，只有"同色格双象无法将死"这条和棋规则用得上。
BB_DARK_SQUARES = 0xAA55_AA55_AA55_AA55
BB_LIGHT_SQUARES = BB_ALL ^ BB_DARK_SQUARES


class Status:
    """What is wrong with a position, if anything.

    ⚠️ This checks the things that actually matter for this project — a position handed to
    the engine by an LLM that misread the board. It is **not** a full legality audit of
    every FEN field. Whatever is not listed here is not checked; do not read more into a
    `VALID` result than that.

    局面有什么毛病（如果有的话）。

    ⚠️ 它只检查**本项目真正会遇到的**那些问题——大脑看错棋盘、给了一个不成立的 FEN。它**不是**对
    FEN 每个字段的完整合法性审计。没列在这里的就是没查；`VALID` 只代表"下面这些都过了"，别多读。
    """

    VALID = 0
    NO_WHITE_KING = 1 << 0
    NO_BLACK_KING = 1 << 1
    TOO_MANY_KINGS = 1 << 2
    TOO_MANY_WHITE_PIECES = 1 << 3
    TOO_MANY_BLACK_PIECES = 1 << 4
    PAWNS_ON_BACKRANK = 1 << 5
    OPPOSITE_CHECK = 1 << 6          # the side NOT to move is in check — impossible
    IMPOSSIBLE_CHECK = 1 << 7        # e.g. three pieces giving check at once

    _NAMES = [
        (NO_WHITE_KING, "NO_WHITE_KING"), (NO_BLACK_KING, "NO_BLACK_KING"),
        (TOO_MANY_KINGS, "TOO_MANY_KINGS"),
        (TOO_MANY_WHITE_PIECES, "TOO_MANY_WHITE_PIECES"),
        (TOO_MANY_BLACK_PIECES, "TOO_MANY_BLACK_PIECES"),
        (PAWNS_ON_BACKRANK, "PAWNS_ON_BACKRANK"),
        (OPPOSITE_CHECK, "OPPOSITE_CHECK"), (IMPOSSIBLE_CHECK, "IMPOSSIBLE_CHECK"),
    ]

    @classmethod
    def describe(cls, value: int) -> str:
        """Human-readable, because this string ends up in an error message the LLM reads
        and is expected to act on. / 给人看的说法——这串字最终会进一条错误消息，大脑要读它并据此
        自我修正。"""
        if not value:
            return "VALID"
        return "|".join(name for bit, name in cls._NAMES if value & bit)


class _LegalMoveGenerator:
    """Lazily generated legal moves. Supports `for m in`, `len()`, `bool()` and `in`,
    which is the whole surface the callers use. / 惰性生成的合法走法。支持遍历、`len()`、
    `bool()` 和 `in`——调用方用到的就这些。"""

    def __init__(self, board: "Board"):
        self.board = board

    def __iter__(self):
        return self.board.generate_legal_moves()

    def __len__(self) -> int:
        return sum(1 for _ in self.board.generate_legal_moves())

    def __bool__(self) -> bool:
        return any(self.board.generate_legal_moves())

    def __contains__(self, move) -> bool:
        return self.board.is_legal(move)

    def __repr__(self) -> str:
        return f"<LegalMoveGenerator ({', '.join(m.uci() for m in self)})>"


class Board:
    """A chess position that can be queried and played on.

    一个可以查询、可以落子的国际象棋局面。"""

    def __init__(self, fen: str | None = STARTING_FEN):
        self.move_stack: list[Move] = []
        self._stack: list[tuple] = []
        if fen is None:
            self._clear()
        else:
            self.set_fen(fen)

    # ---------------------------------------------------------------- setup / 初始化 ---

    def _clear(self) -> None:
        self.pawns = self.knights = self.bishops = BB_EMPTY
        self.rooks = self.queens = self.kings = BB_EMPTY
        self.occupied_co = [BB_EMPTY, BB_EMPTY]      # [BLACK][WHITE] via bool-as-index
        self.occupied = BB_EMPTY
        self.turn = WHITE
        self.castling_rights = BB_EMPTY
        self.ep_square: int | None = None
        self.halfmove_clock = 0
        self.fullmove_number = 1
        self.move_stack.clear()
        self._stack.clear()
        self._repetitions: dict[int, int] = {}
        self._hash = 0

    def _set_piece_at(self, square: int, piece_type: int, color: bool) -> None:
        bb = BB_SQUARES[square]
        if piece_type == PAWN:
            self.pawns |= bb
        elif piece_type == KNIGHT:
            self.knights |= bb
        elif piece_type == BISHOP:
            self.bishops |= bb
        elif piece_type == ROOK:
            self.rooks |= bb
        elif piece_type == QUEEN:
            self.queens |= bb
        else:
            self.kings |= bb
        self.occupied |= bb
        self.occupied_co[color] |= bb

    def _remove_piece_at(self, square: int) -> int:
        """Take whatever is on `square` off the board, returning its type (0 if empty).
        / 把 `square` 上的子拿掉，返回它的类型（空格返回 0）。"""
        piece_type = self.piece_type_at(square)
        if not piece_type:
            return 0
        mask = ~BB_SQUARES[square]
        if piece_type == PAWN:
            self.pawns &= mask
        elif piece_type == KNIGHT:
            self.knights &= mask
        elif piece_type == BISHOP:
            self.bishops &= mask
        elif piece_type == ROOK:
            self.rooks &= mask
        elif piece_type == QUEEN:
            self.queens &= mask
        else:
            self.kings &= mask
        self.occupied &= mask
        self.occupied_co[WHITE] &= mask
        self.occupied_co[BLACK] &= mask
        return piece_type

    # ------------------------------------------------------------ inspection / 查询 ---

    def piece_type_at(self, square: int) -> int:
        bb = BB_SQUARES[square]
        if not self.occupied & bb:
            return 0
        if self.pawns & bb:
            return PAWN
        if self.knights & bb:
            return KNIGHT
        if self.bishops & bb:
            return BISHOP
        if self.rooks & bb:
            return ROOK
        if self.queens & bb:
            return QUEEN
        return KING

    def color_at(self, square: int) -> bool | None:
        bb = BB_SQUARES[square]
        if self.occupied_co[WHITE] & bb:
            return WHITE
        if self.occupied_co[BLACK] & bb:
            return BLACK
        return None

    def piece_at(self, square: int) -> Piece | None:
        piece_type = self.piece_type_at(square)
        return Piece(piece_type, bool(self.occupied_co[WHITE] & BB_SQUARES[square])) \
            if piece_type else None

    def piece_map(self) -> dict[int, Piece]:
        """Every occupied square -> the piece on it. / 每个有子的格子 → 上面的子。"""
        return {sq: self.piece_at(sq) for sq in scan_forward(self.occupied)}

    def king(self, color: bool) -> int | None:
        bb = self.kings & self.occupied_co[color]
        return msb(bb) if bb else None

    # ------------------------------------------------------------- attacks / 攻击 ---

    def attacks_mask(self, square: int) -> int:
        """Everything the piece on `square` attacks, given the current occupancy.
        / 当前占位下，`square` 上那个子攻击到的所有格。"""
        bb = BB_SQUARES[square]
        if self.pawns & bb:
            return BB_PAWN_ATTACKS[bool(self.occupied_co[WHITE] & bb)][square]
        if self.knights & bb:
            return BB_KNIGHT_ATTACKS[square]
        if self.kings & bb:
            return BB_KING_ATTACKS[square]
        if self.bishops & bb:
            return bishop_attacks(square, self.occupied)
        if self.rooks & bb:
            return rook_attacks(square, self.occupied)
        if self.queens & bb:
            return queen_attacks(square, self.occupied)
        return BB_EMPTY

    def _attackers_mask(self, color: bool, square: int, occupied: int) -> int:
        """Which of `color`'s pieces attack `square`, for a given occupancy.

        The trick here reads backwards at first: to find enemy knights attacking a square,
        look at where a knight *on that square* could go. Attack relations are symmetric
        for every piece except pawns, which is why pawns use the opposite colour's table.

        在给定占位下，`color` 方哪些子攻击着 `square`。

        这里的技巧初看是反着的：要找出攻击某格的对方的马，就看**站在那一格上的马**能跳到哪。
        除了兵以外，所有子的攻击关系都是对称的——兵不对称，所以兵要查**反色**的那张表。
        """
        rank_file = rook_attacks(square, occupied)
        diag = bishop_attacks(square, occupied)
        return (((BB_KNIGHT_ATTACKS[square] & self.knights)
                 | (rank_file & (self.rooks | self.queens))
                 | (diag & (self.bishops | self.queens))
                 | (BB_KING_ATTACKS[square] & self.kings)
                 | (BB_PAWN_ATTACKS[not color][square] & self.pawns))
                & self.occupied_co[color])

    def attackers_mask(self, color: bool, square: int) -> int:
        return self._attackers_mask(color, square, self.occupied)

    def is_attacked_by(self, color: bool, square: int) -> bool:
        return bool(self.attackers_mask(color, square))

    def _attacked_for_king(self, path: int, occupied: int) -> bool:
        """Is any square in `path` attacked by the opponent?

        `occupied` is passed in rather than read from the board because of one specific
        trap: when the king runs away from a checking rook, it must not step *backwards*
        along the same line. With the king still on the board it blocks the rook's view of
        the square behind it, so that square looks safe. Removing the king first is what
        makes the answer correct.

        `path` 里有没有格子正被对方攻击？

        `occupied` 是**传进来**的而不是直接读棋盘，因为有一个特定的坑：王躲避车的将军时，**不能沿
        着同一条线往后退**。可如果王还在棋盘上，它自己会挡住车看向它身后那一格的视线，于是那一格
        看起来是安全的。先把王拿掉再问，答案才对。
        """
        opponent = not self.turn
        return any(self._attackers_mask(opponent, sq, occupied) for sq in scan_forward(path))

    def _slider_blockers(self, king: int) -> int:
        """My own pieces that are pinned against my king.

        Look outwards from the king along the rook lines and the bishop lines. Any enemy
        slider found on such a line is a potential pinner ("sniper"). If exactly one piece
        stands between it and the king, that piece is pinned.

        我自己**被牵制在王前面**的那些子。

        从王沿着车的线和象的线往外看。落在这些线上的对方滑行子都是潜在的牵制者（"狙击手"）。
        如果它和王之间**恰好只隔着一个子**，那个子就是被牵制的。
        """
        snipers = ((rook_attacks(king, 0) & (self.queens | self.rooks))
                   | (bishop_attacks(king, 0) & (self.queens | self.bishops)))
        blockers = BB_EMPTY
        for sniper in scan_forward(snipers & self.occupied_co[not self.turn]):
            between = BB_BETWEEN[king][sniper] & self.occupied
            # `b & (b - 1)` clears the lowest set bit; if the result is 0 there was exactly
            # one. / `b & (b - 1)` 会清掉最低位的 1；结果为 0 就说明原本只有一个。
            if between and not (between & (between - 1)):
                blockers |= between
        return blockers & self.occupied_co[self.turn]

    # -------------------------------------------------- move generation / 走子生成 ---

    def generate_pseudo_legal_moves(self, from_mask: int = BB_ALL, to_mask: int = BB_ALL):
        """Everything that moves like a legal move but might leave the king en prise.
        / 走法形状都对、但可能把自己的王送掉的那些走法。"""
        our_pieces = self.occupied_co[self.turn]

        # --- pieces other than pawns / 兵以外的子 ---
        for from_sq in scan_forward(our_pieces & ~self.pawns & from_mask):
            moves = self.attacks_mask(from_sq) & ~our_pieces & to_mask
            for to_sq in scan_forward(moves):
                yield Move(from_sq, to_sq)

        # --- castling / 易位 ---
        if from_mask & self.kings:
            yield from self.generate_castling_moves(from_mask, to_mask)

        pawns = self.pawns & our_pieces & from_mask
        if not pawns:
            return

        # --- pawn captures / 兵吃子 ---
        for from_sq in scan_forward(pawns):
            targets = (BB_PAWN_ATTACKS[self.turn][from_sq]
                       & self.occupied_co[not self.turn] & to_mask)
            for to_sq in scan_forward(targets):
                yield from self._pawn_moves(from_sq, to_sq)

        # --- pawn pushes / 兵前进 ---
        # Done as a whole-set shift rather than per pawn: shifting the pawn bitboard up one
        # rank and masking out occupied squares advances every pawn at once.
        # 整体位移，而不是逐个兵算：把兵的位棋盘整体上移一行、再抠掉有子的格，就等于所有兵同时前进一步。
        if self.turn == WHITE:
            single = (pawns << 8) & ~self.occupied & BB_ALL
            double = ((single & BB_RANKS[2]) << 8) & ~self.occupied
            back1, back2 = -8, -16
        else:
            single = (pawns >> 8) & ~self.occupied
            double = ((single & BB_RANKS[5]) >> 8) & ~self.occupied
            back1, back2 = 8, 16

        for to_sq in scan_forward(single & to_mask):
            yield from self._pawn_moves(to_sq + back1, to_sq)
        for to_sq in scan_forward(double & to_mask):
            yield Move(to_sq + back2, to_sq)

        # --- en passant / 吃过路兵 ---
        if self.ep_square is not None and not self.occupied & BB_SQUARES[self.ep_square]:
            yield from self.generate_pseudo_legal_ep(from_mask, to_mask)

    def _pawn_moves(self, from_sq: int, to_sq: int):
        """One pawn move, expanded into four if it lands on the last rank.
        / 一步兵的走法；落到底线时展开成四种升变。"""
        if square_rank(to_sq) in (0, 7):
            for promo in (QUEEN, ROOK, BISHOP, KNIGHT):
                yield Move(from_sq, to_sq, promo)
        else:
            yield Move(from_sq, to_sq)

    def generate_pseudo_legal_ep(self, from_mask: int = BB_ALL, to_mask: int = BB_ALL):
        if self.ep_square is None or not BB_SQUARES[self.ep_square] & to_mask:
            return
        if self.occupied & BB_SQUARES[self.ep_square]:
            return
        capturers = (self.pawns & self.occupied_co[self.turn] & from_mask
                     & BB_PAWN_ATTACKS[not self.turn][self.ep_square])
        for from_sq in scan_forward(capturers):
            yield Move(from_sq, self.ep_square)

    def generate_castling_moves(self, from_mask: int = BB_ALL, to_mask: int = BB_ALL):
        """Standard castling only — this library does not implement Chess960.

        Three conditions, and the third is the one people forget: the king may not castle
        out of check, **through** an attacked square, or into check.

        只支持标准易位——本库不实现 Chess960。

        三个条件，第三条最常被忘：王**不能**在被将时易位、不能**经过**被攻击的格子、也不能易位到
        被攻击的格子上。
        """
        backrank = BB_RANKS[0] if self.turn == WHITE else BB_RANKS[7]
        king_sq = E1 if self.turn == WHITE else E8
        king_bb = self.kings & self.occupied_co[self.turn] & backrank & from_mask
        if not king_bb or msb(king_bb) != king_sq:
            return
        if self.is_attacked_by(not self.turn, king_sq):
            return

        rights = self.castling_rights & backrank
        # (rook square, squares that must be empty, squares the king passes through, king destination)
        # （车所在格，必须为空的格，王要经过的格，王的落点）
        plans = (
            (king_sq + 3, (king_sq + 1, king_sq + 2), (king_sq + 1, king_sq + 2), king_sq + 2),
            (king_sq - 4, (king_sq - 1, king_sq - 2, king_sq - 3), (king_sq - 1, king_sq - 2),
             king_sq - 2),
        )
        for rook_sq, empties, path, dest in plans:
            if not rights & BB_SQUARES[rook_sq]:
                continue
            if any(self.occupied & BB_SQUARES[sq] for sq in empties):
                continue
            if any(self.is_attacked_by(not self.turn, sq) for sq in path):
                continue
            if BB_SQUARES[dest] & to_mask:
                yield Move(king_sq, dest)

    def _generate_evasions(self, king: int, checkers: int, from_mask: int, to_mask: int):
        """Only the moves that could possibly answer a check. / 只生成有可能应将的走法。"""
        sliders = checkers & (self.bishops | self.rooks | self.queens)

        # Squares behind the king along the checking line: stepping there is still check.
        # 沿将军线在王身后的那些格：退到那里仍然在被将。
        attacked = BB_EMPTY
        for checker in scan_forward(sliders):
            attacked |= BB_RAYS[king][checker] & ~BB_SQUARES[checker]

        if BB_SQUARES[king] & from_mask:
            targets = (BB_KING_ATTACKS[king] & ~self.occupied_co[self.turn]
                       & ~attacked & to_mask)
            for to_sq in scan_forward(targets):
                yield Move(king, to_sq)

        # Two pieces checking at once cannot both be dealt with — the king must move.
        # 同时被两个子将军时不可能一手解决两个——只能动王。
        checker = msb(checkers)
        if BB_SQUARES[checker] != checkers:
            return

        target = BB_BETWEEN[king][checker] | checkers
        yield from self.generate_pseudo_legal_moves(~self.kings & from_mask, target & to_mask)

        # Capturing the checking pawn en passant does not land on `target`, so it has to be
        # generated separately. / 用吃过路兵吃掉将军的那个兵，落点不在 `target` 里，得单独生成。
        if self.ep_square is not None and not BB_SQUARES[self.ep_square] & target:
            last_double = self.ep_square + (-8 if self.turn == WHITE else 8)
            if last_double == checker:
                yield from self.generate_pseudo_legal_ep(from_mask, to_mask)

    def generate_legal_moves(self, from_mask: int = BB_ALL, to_mask: int = BB_ALL):
        king = self.king(self.turn)
        if king is None:
            # No king on the board. Not a real game, but perft suites and hand-written test
            # positions do it, so do something sensible instead of crashing.
            # 棋盘上没有王。这不是真实对局，但 perft 测试集和手写测试局面里会出现，所以别崩，
            # 给个合理的行为。
            yield from self.generate_pseudo_legal_moves(from_mask, to_mask)
            return

        blockers = self._slider_blockers(king)
        checkers = self.attackers_mask(not self.turn, king)
        gen = (self._generate_evasions(king, checkers, from_mask, to_mask) if checkers
               else self.generate_pseudo_legal_moves(from_mask, to_mask))
        for move in gen:
            if self._is_safe(king, blockers, move):
                yield move

    def _is_safe(self, king: int, blockers: int, move: Move) -> bool:
        """Does this move leave my own king safe? / 这步走完，我的王安全吗？"""
        if move.from_square == king:
            if self.is_castling(move):
                return True          # already fully checked while generating / 生成时已查全
            # Ask with the king removed — see `_attacked_for_king`.
            # 把王拿掉再问——原因见 `_attacked_for_king`。
            return not self._attacked_for_king(BB_SQUARES[move.to_square],
                                               self.occupied & ~BB_SQUARES[king])
        if self.is_en_passant(move):
            return self._ep_is_safe(king, move)
        # Not pinned, or still moving along the pin line. `BB_RAYS[from][to]` is the whole
        # infinite line through both squares, so "does it still contain my king" is exactly
        # the right question. / 没被牵制，或者仍走在牵制线上。`BB_RAYS[from][to]` 是穿过这两格的
        # 整条直线，所以"它还包含我的王吗"正是该问的问题。
        return (not blockers & BB_SQUARES[move.from_square]
                or bool(BB_RAYS[move.from_square][move.to_square] & BB_SQUARES[king]))

    def _ep_is_safe(self, king: int, move: Move) -> bool:
        """En passant needs its own test because it is the only move that removes a piece
        from a square the mover does not land on. Two pawns can vanish from the same rank
        at once, which can expose a king to a rook that neither pawn was individually
        pinned against.

        吃过路兵要单独判，因为它是**唯一**一种"吃掉的子不在落点上"的走法。同一横行上会一次消失
        两个兵，从而把王暴露给一个车——而这两个兵单独看**谁都不算被牵制**。
        """
        captured = move.to_square + (-8 if self.turn == WHITE else 8)
        occupied = ((self.occupied & ~BB_SQUARES[move.from_square] & ~BB_SQUARES[captured])
                    | BB_SQUARES[move.to_square])
        opponent = self.occupied_co[not self.turn]
        return not ((rook_attacks(king, occupied) & opponent & (self.rooks | self.queens))
                    or (bishop_attacks(king, occupied) & opponent
                        & (self.bishops | self.queens)))

    @property
    def legal_moves(self) -> _LegalMoveGenerator:
        return _LegalMoveGenerator(self)

    def is_legal(self, move) -> bool:
        if not isinstance(move, Move) or not move:
            return False
        return any(m == move for m in self.generate_legal_moves(
            BB_SQUARES[move.from_square], BB_SQUARES[move.to_square]))

    # ------------------------------------------------- move classification / 走法分类 ---

    def is_castling(self, move: Move) -> bool:
        if not self.kings & BB_SQUARES[move.from_square]:
            return False
        return abs(square_file(move.to_square) - square_file(move.from_square)) > 1

    def is_en_passant(self, move: Move) -> bool:
        return (self.ep_square == move.to_square
                and bool(self.pawns & BB_SQUARES[move.from_square])
                and abs(move.to_square - move.from_square) in (7, 9)
                and not self.occupied & BB_SQUARES[move.to_square])

    def is_capture(self, move: Move) -> bool:
        return (bool(BB_SQUARES[move.to_square] & self.occupied_co[not self.turn])
                or self.is_en_passant(move))

    def gives_check(self, move: Move) -> bool:
        """Play it, look, take it back. Cheap enough because push/pop here is just tuple
        bookkeeping. / 走一步、看一眼、再收回来。这里的 push/pop 只是元组记账，足够便宜。"""
        self.push(move)
        try:
            return self.is_check()
        finally:
            self.pop()

    # ------------------------------------------------------- playing moves / 落子 ---

    def push(self, move: Move) -> None:
        """Play `move`, remembering everything needed to take it back.

        **A note on Python.** Chess engines in C use "make/unmake": they mutate the board
        and reverse the mutation later, because copying a board structure is expensive.
        Here the entire position is nine Python integers, and integers are immutable — so
        stashing nine references in a tuple costs almost nothing and reversing a move is a
        plain assignment. Copy-and-restore is both faster to write and impossible to get
        subtly wrong, which matters more than the last few percent.

        走 `move`，并把"悔棋需要的一切"记下来。

        **一个关于 Python 的说明。** C 写的引擎用 make/unmake：修改棋盘、之后再把修改逆回去，
        因为拷贝棋盘结构很贵。而这里整个局面就是九个 Python 整数，整数又是不可变的——把九个引用塞
        进一个元组几乎不花钱，悔棋就是一次赋值。**"快照+还原"既好写、又不可能写出那种微妙的错**，
        这比省下最后百分之几更重要。
        """
        self._stack.append((
            self.pawns, self.knights, self.bishops, self.rooks, self.queens, self.kings,
            self.occupied_co[BLACK], self.occupied_co[WHITE], self.occupied,
            self.turn, self.castling_rights, self.ep_square,
            self.halfmove_clock, self.fullmove_number, self._hash,
        ))
        self.move_stack.append(move)

        ep_square, self.ep_square = self.ep_square, None
        self.halfmove_clock += 1
        if self.turn == BLACK:
            self.fullmove_number += 1

        from_bb = BB_SQUARES[move.from_square]
        to_bb = BB_SQUARES[move.to_square]
        piece_type = self.piece_type_at(move.from_square)
        color = self.turn

        # Castling rights die when the king moves, or when either a rook leaves its corner
        # or something captures on that corner. Masking by both endpoints covers all of it.
        # 王一动，易位权全没；车离开角上、或有子吃到那个角上，对应那侧的权利也没了。
        # 用起点和终点一起做掩码，正好把这些情形全覆盖。
        self.castling_rights &= ~(from_bb | to_bb)
        if piece_type == KING:
            self.castling_rights &= ~(BB_RANKS[0] if color == WHITE else BB_RANKS[7])

        self._remove_piece_at(move.from_square)

        if piece_type == PAWN:
            self.halfmove_clock = 0
            diff = move.to_square - move.from_square
            if abs(diff) == 16:
                self.ep_square = move.from_square + (8 if color == WHITE else -8)
            elif (move.to_square == ep_square and abs(diff) in (7, 9)
                    and not self.occupied & to_bb):
                self._remove_piece_at(ep_square + (-8 if color == WHITE else 8))

        if self.occupied & to_bb:
            self.halfmove_clock = 0
            self._remove_piece_at(move.to_square)

        self._set_piece_at(move.to_square, move.promotion or piece_type, color)

        if piece_type == KING and abs(move.to_square - move.from_square) == 2:
            if move.to_square > move.from_square:            # O-O
                rook_from, rook_to = move.from_square + 3, move.from_square + 1
            else:                                            # O-O-O
                rook_from, rook_to = move.from_square - 4, move.from_square - 1
            self._remove_piece_at(rook_from)
            self._set_piece_at(rook_to, ROOK, color)

        self.turn = not color

        # The hash is rebuilt from scratch rather than updated incrementally, and that is a
        # measured decision, not an oversight.
        #
        # XOR-ing a handful of keys per move would be perhaps five times cheaper, and a
        # profile confirms this line is the single largest cost in `push`. It is not being
        # done because the budget does not require it: the search this library was written
        # for finishes a depth-3 middlegame position in 1.3 s against a 1.5 s cap, and the
        # engine's iterative deepening bounds the wall clock regardless. An incremental
        # hash that drifts out of sync fails *silently* — repetition detection just stops
        # working — so it is not worth buying speed nobody needs with a bug class nobody
        # would notice.
        #
        # Revisit when a transposition table arrives: that is when hashing moves onto the
        # critical path for real. `_compute_hash` is already written to serve as the oracle
        # to check an incremental version against.
        #
        # 哈希是**整个重算**而不是增量更新的，这是量过之后的决定，不是疏忽。
        #
        # 每步只异或几个键大约能便宜五倍，profile 也确认这一行是 `push` 里最大的开销。不做的原因是
        # 预算根本不紧张：这个库要服务的那个搜索，中局 depth 3 用 1.3 秒、上限是 1.5 秒，而且引擎的
        # 迭代加深本来就兜住了墙钟时间。增量哈希一旦跑偏是**静默失败**——重复局面判定直接不工作
        # ——花一个没人会发现的 bug 类别去换没人需要的速度，不划算。
        #
        # 等置换表来了再回头改：那时候哈希才真正上关键路径。`_compute_hash` 已经按"给增量版本当
        # 标准答案"的用途写好了。
        self._hash = self._compute_hash()
        self._repetitions[self._hash] = self._repetitions.get(self._hash, 0) + 1

    def pop(self) -> Move:
        """Undo the last move and return it. / 撤销最后一步并返回它。"""
        count = self._repetitions.get(self._hash, 0)
        if count <= 1:
            self._repetitions.pop(self._hash, None)
        else:
            self._repetitions[self._hash] = count - 1

        (self.pawns, self.knights, self.bishops, self.rooks, self.queens, self.kings,
         black, white, self.occupied, self.turn, self.castling_rights, self.ep_square,
         self.halfmove_clock, self.fullmove_number, self._hash) = self._stack.pop()
        self.occupied_co = [black, white]
        return self.move_stack.pop()

    # ------------------------------------------------------------- hashing / 哈希 ---

    def _ep_hash_square(self) -> int | None:
        """The en-passant square that currently belongs in the hash, or None.

        Why this is not simply `self.ep_square`: a FEN routinely records an en-passant
        square that no pawn can actually use. Two positions that differ only in such a
        phantom square are the same position by any rule that matters, so folding it into
        the hash would give them different names and **repetition detection would quietly
        stop working**.

        The cheap test comes first on purpose. Asking "does any of my pawns even attack
        that square" is one bitboard AND; only if that passes is it worth generating moves
        to find out whether the capture is truly legal. The expensive branch then almost
        never runs.

        当前**该进哈希**的那个吃过路兵格，没有则为 None。

        为什么不能直接用 `self.ep_square`：FEN 里经常记着一个根本没有兵能吃的过路兵格。两个只在这种
        幽灵格上有差别的局面，按任何有意义的规则都是同一个局面；把它折进哈希，它们就会得到不同的名字，
        **重复局面判定会静悄悄地失效**。

        便宜的判断有意放在前面：「我到底有没有兵攻击着那一格」只是一次按位与；只有它过了，才值得生成
        走法去确认这步吃子是不是真的合法。于是那条昂贵的分支几乎从不执行。
        """
        ep = self.ep_square
        if ep is None:
            return None
        if not (BB_PAWN_ATTACKS[not self.turn][ep] & self.pawns & self.occupied_co[self.turn]):
            return None
        # ⚠️ The `is_en_passant` filter is not optional. The en-passant square is empty by
        # definition, so a knight or a rook can legally move onto it — without this filter
        # such a move would be mistaken for an available en-passant capture.
        # ⚠️ 这个 `is_en_passant` 过滤**不能省**。吃过路兵那一格按定义是空的，所以马或车完全可以合法
        # 走上去——没有这层过滤，那种走法会被误当成"能吃过路兵"。
        return ep if any(self.is_en_passant(m) for m in
                         self.generate_legal_moves(BB_ALL, BB_SQUARES[ep])) else None

    def _compute_hash(self) -> int:
        """Build the key from scratch.

        Used when a position arrives out of nowhere (a FEN), and — more importantly — as
        the oracle the incremental update in `push()` is checked against in the tests. An
        incremental hash that drifts is a nasty bug: nothing crashes, repetition detection
        just silently misfires. Having a slow, obviously-correct version to compare with is
        what keeps the fast version honest.

        从零把键算出来。

        用在"局面凭空出现"的时候（给一个 FEN），以及——更重要的——**当作测试里检验 `push()` 增量更新
        的标准答案**。增量哈希一旦跑偏是很难缠的 bug：什么都不崩，只是重复局面判定悄悄失灵。
        留一份慢但显然正确的版本来对拍，才管得住那个快版本。
        """
        key = 0
        for color in COLORS:
            keys = PIECE_KEYS[color]
            for sq in scan_forward(self.occupied_co[color]):
                key ^= keys[self.piece_type_at(sq)][sq]
        for sq in scan_forward(self.castling_rights & BB_CORNERS):
            key ^= CASTLING_KEYS[sq]
        if self.turn == BLACK:
            key ^= TURN_KEY
        ep = self._ep_hash_square()
        if ep is not None:
            key ^= EP_FILE_KEYS[square_file(ep)]
        return key

    # ------------------------------------------------- game termination / 终局判定 ---

    def is_check(self) -> bool:
        king = self.king(self.turn)
        return king is not None and self.is_attacked_by(not self.turn, king)

    def is_checkmate(self) -> bool:
        return self.is_check() and not any(self.generate_legal_moves())

    def is_stalemate(self) -> bool:
        return not self.is_check() and not any(self.generate_legal_moves())

    def has_insufficient_material(self, color: bool) -> bool:
        """Could `color` still mate, given enough cooperation from the opponent?
        / 就算对方全力配合，`color` 还有可能将死吗？"""
        ours = self.occupied_co[color]
        if ours & (self.pawns | self.rooks | self.queens):
            return False
        if ours & self.knights:
            # A lone knight cannot force mate, and cannot mate at all unless the opponent
            # has material to be mated with. / 单马无法逼杀；除非对方还有子可以配合，否则根本
            # 构不成将死。
            return (popcount(ours) <= 2
                    and not (self.occupied_co[not color] & ~self.kings & ~self.queens))
        if ours & self.bishops:
            # Bishops all on one colour of square can never cover the other colour.
            # 所有象都在同一色格上时，另一种颜色的格子永远够不着。
            same_color = (not self.bishops & BB_DARK_SQUARES
                          or not self.bishops & BB_LIGHT_SQUARES)
            return same_color and not self.pawns and not self.knights
        return True

    def is_insufficient_material(self) -> bool:
        return all(self.has_insufficient_material(color) for color in COLORS)

    def _is_halfmoves(self, n: int) -> bool:
        # Checkmate takes precedence over any move-counter draw, hence the legal-move test.
        # 将死优先于任何"步数计时"的和棋，所以要顺带检查还有没有合法走法。
        return self.halfmove_clock >= n and any(self.generate_legal_moves())

    def is_fifty_moves(self) -> bool:
        return self._is_halfmoves(100)

    def is_seventyfive_moves(self) -> bool:
        return self._is_halfmoves(150)

    def is_repetition(self, count: int = 3) -> bool:
        return self._repetitions.get(self._hash, 0) >= count

    def is_fivefold_repetition(self) -> bool:
        return self.is_repetition(5)

    def is_game_over(self) -> bool:
        """Only the endings that need no claim from a player: checkmate, stalemate, dead
        position, and the two automatic draws. The fifty-move and threefold rules require
        someone to claim them, so they are deliberately not here.

        只算**不需要任何一方提出**的终局：将死、逼和、子力不足，以及那两条自动和棋。五十步和三次
        重复需要有人主动提出，所以**有意**不算在内。
        """
        return (self.is_checkmate() or self.is_stalemate() or self.is_insufficient_material()
                or self.is_seventyfive_moves() or self.is_fivefold_repetition())

    def result(self) -> str:
        """"1-0", "0-1", "1/2-1/2", or "*" while the game is still running.
        / "1-0"、"0-1"、"1/2-1/2"；对局未完则是 "*"。"""
        if self.is_checkmate():
            return "0-1" if self.turn == WHITE else "1-0"
        if (self.is_stalemate() or self.is_insufficient_material()
                or self.is_seventyfive_moves() or self.is_fivefold_repetition()):
            return "1/2-1/2"
        return "*"

    # ------------------------------------------------------------ validity / 合法性 ---

    def status(self) -> int:
        errors = Status.VALID
        if not self.occupied_co[WHITE] & self.kings:
            errors |= Status.NO_WHITE_KING
        if not self.occupied_co[BLACK] & self.kings:
            errors |= Status.NO_BLACK_KING
        if popcount(self.kings) > 2:
            errors |= Status.TOO_MANY_KINGS
        if popcount(self.occupied_co[WHITE]) > 16:
            errors |= Status.TOO_MANY_WHITE_PIECES
        if popcount(self.occupied_co[BLACK]) > 16:
            errors |= Status.TOO_MANY_BLACK_PIECES
        if self.pawns & BB_BACKRANKS:
            errors |= Status.PAWNS_ON_BACKRANK

        # The side that just moved must not be in check — they would have been obliged to
        # deal with it. / 刚走完的那一方不可能还在被将——那一步本来就该先应将。
        opponent_king = self.king(not self.turn)
        if opponent_king is not None and self.is_attacked_by(self.turn, opponent_king):
            errors |= Status.OPPOSITE_CHECK

        our_king = self.king(self.turn)
        if our_king is not None and popcount(self.attackers_mask(not self.turn, our_king)) > 2:
            errors |= Status.IMPOSSIBLE_CHECK
        return errors

    def is_valid(self) -> bool:
        return self.status() == Status.VALID

    # ------------------------------------------------------------------ FEN / FEN ---

    def board_fen(self) -> str:
        """Just the piece placement field. / 只有"子在哪"那一段。"""
        rows = []
        for rank in range(7, -1, -1):
            row, empty = "", 0
            for file in range(8):
                piece = self.piece_at(rank * 8 + file)
                if piece is None:
                    empty += 1
                    continue
                if empty:
                    row += str(empty)
                    empty = 0
                row += piece.symbol()
            if empty:
                row += str(empty)
            rows.append(row)
        return "/".join(rows)

    def fen(self) -> str:
        castling = "".join(s for sq, s in ((H1, "K"), (A1, "Q"), (H8, "k"), (A8, "q"))
                           if self.castling_rights & BB_SQUARES[sq]) or "-"
        ep = SQUARE_NAMES[self.ep_square] if self.ep_square is not None else "-"
        return (f"{self.board_fen()} {'w' if self.turn == WHITE else 'b'} {castling} "
                f"{ep} {self.halfmove_clock} {self.fullmove_number}")

    def set_fen(self, fen: str) -> None:
        parts = fen.split()
        if len(parts) < 4:
            raise ValueError(f"FEN must have at least 4 fields: {fen!r}")
        placement, turn, castling, ep = parts[:4]
        halfmove = parts[4] if len(parts) > 4 else "0"
        fullmove = parts[5] if len(parts) > 5 else "1"

        rows = placement.split("/")
        if len(rows) != 8:
            raise ValueError(f"FEN board must have 8 ranks: {placement!r}")

        self._clear()
        for rank_index, row in enumerate(rows):
            rank = 7 - rank_index
            file = 0
            for ch in row:
                if ch.isdigit():
                    file += int(ch)
                elif ch in "pnbrqkPNBRQK":
                    if file > 7:
                        raise ValueError(f"too many squares in rank: {row!r}")
                    self._set_piece_at(rank * 8 + file, PIECE_SYMBOLS.index(ch.lower()),
                                       ch.isupper())
                    file += 1
                else:
                    raise ValueError(f"invalid character in FEN board: {ch!r}")
            if file != 8:
                raise ValueError(f"rank does not add up to 8 squares: {row!r}")

        if turn not in ("w", "b"):
            raise ValueError(f"side to move must be 'w' or 'b': {turn!r}")
        self.turn = WHITE if turn == "w" else BLACK

        if castling != "-":
            for ch in castling:
                sq = {"K": H1, "Q": A1, "k": H8, "q": A8}.get(ch)
                if sq is None:
                    raise ValueError(f"invalid castling field: {castling!r}")
                self.castling_rights |= BB_SQUARES[sq]
            # Rights are meaningless without the king and rook actually being home; strip
            # the ones a sloppy FEN claims. / 王和车不在原位时权利无从谈起；把马虎的 FEN 里那些
            # 站不住的权利去掉。
            for rook_sq, king_sq, color in ((H1, E1, WHITE), (A1, E1, WHITE),
                                            (H8, E8, BLACK), (A8, E8, BLACK)):
                if not (self.kings & self.occupied_co[color] & BB_SQUARES[king_sq]
                        and self.rooks & self.occupied_co[color] & BB_SQUARES[rook_sq]):
                    self.castling_rights &= ~BB_SQUARES[rook_sq]

        if ep != "-":
            try:
                self.ep_square = SQUARE_NAMES.index(ep)
            except ValueError:
                raise ValueError(f"invalid en passant square: {ep!r}") from None

        try:
            self.halfmove_clock = int(halfmove)
            self.fullmove_number = max(int(fullmove), 1)
        except ValueError:
            raise ValueError(f"invalid move counters: {halfmove!r} {fullmove!r}") from None

        self._hash = self._compute_hash()
        self._repetitions = {self._hash: 1}

    # ------------------------------------------------------------------------------- --

    def copy(self) -> "Board":
        return Board(self.fen())

    def __repr__(self) -> str:
        return f"Board({self.fen()!r})"

    def __str__(self) -> str:
        rows = []
        for rank in range(7, -1, -1):
            rows.append(" ".join((self.piece_at(rank * 8 + f).symbol()
                                  if self.piece_at(rank * 8 + f) else ".")
                                 for f in range(8)))
        return "\n".join(rows)
