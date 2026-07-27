"""The rules that are easy to get wrong, tested one by one.

Perft proves the move counts are right; it does not say *why* when they are not. These
tests name each rule, so a failure points at the rule instead of at a number.

那些最容易写错的规则，一条一条地测。

Perft 能证明走法总数对不对，但数字不对时它不会告诉你**为什么**。这些测试给每条规则起了名字，
挂掉时指向的是规则本身，而不是一个数。
"""
from __future__ import annotations

import anima_chess as ac
from anima_chess import Board, Move


def ucis(board: Board) -> set[str]:
    return {m.uci() for m in board.legal_moves}


# --- castling / 易位 -------------------------------------------------------------------

def test_castling_both_sides_available():
    b = Board("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    assert {"e1g1", "e1c1"} <= ucis(b)


def test_castling_blocked_by_own_piece():
    b = Board("r3k2r/8/8/8/8/8/8/R3KB1R w KQkq - 0 1")
    assert "e1g1" not in ucis(b), "a bishop on f1 blocks / f1 有象挡着"
    assert "e1c1" in ucis(b)


def test_cannot_castle_out_of_check():
    b = Board("r3k2r/8/8/8/8/8/4r3/R3K2R w KQkq - 0 1")
    assert "e1g1" not in ucis(b) and "e1c1" not in ucis(b)


def test_cannot_castle_through_an_attacked_square():
    """The one people forget: f1 is attacked, so the king may not pass over it even though
    both e1 and g1 are safe. / 最常被忘的一条：f1 被攻击，即使 e1 和 g1 都安全，王也不能从它上面过。"""
    b = Board("r3k2r/8/8/8/8/8/5r2/R3K2R w KQkq - 0 1")
    assert "e1g1" not in ucis(b)
    assert "e1c1" in ucis(b), "the queenside path is clear / 后翼那侧没问题"


def test_queenside_castling_allows_attacked_b_file():
    """b1 is attacked but the king never stands there, so O-O-O stays legal — the rule is
    about the king's path, not the rook's. / b1 被攻击，但王根本不经过那里，所以长易位仍合法
    ——这条规则管的是**王**走过的格，不是车走过的格。"""
    b = Board("r3k2r/8/8/8/8/8/1r6/R3K2R w KQkq - 0 1")
    assert "e1c1" in ucis(b)


def test_castling_rights_die_when_the_rook_is_captured():
    b = Board("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    b.push(Move.from_uci("a1a8"))                    # white rook takes on a8 / 白车吃 a8
    assert "q" not in b.fen().split()[2], "black lost queenside rights / 黑方失去长易位权"


def test_castling_moves_the_rook_too():
    b = Board("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    b.push(Move.from_uci("e1g1"))
    assert b.piece_at(ac.parse_square("f1")).piece_type == ac.ROOK
    assert b.piece_at(ac.parse_square("h1")) is None
    b.pop()
    assert b.fen() == "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1"


# --- en passant / 吃过路兵 --------------------------------------------------------------

def test_en_passant_is_available_and_removes_the_right_pawn():
    b = Board("4k3/8/8/8/4p3/8/3P4/4K3 w - - 0 1")
    b.push(Move.from_uci("d2d4"))                    # double push next to a black pawn
    assert "e4d3" in ucis(b)
    b.push(Move.from_uci("e4d3"))
    assert b.piece_at(ac.parse_square("d4")) is None, "the passed pawn is gone / 被吃的兵不在了"
    assert b.piece_at(ac.parse_square("d3")).piece_type == ac.PAWN


def test_en_passant_forbidden_when_it_would_expose_the_king():
    """The classic trap. Capturing exd3 removes two pawns from rank 4 at once, opening the
    black king to the white queen on h4 — even though neither pawn was pinned on its own.

    最经典的坑。走 exd3 会一次拿掉第 4 横行上的两个兵，把黑王暴露给 h4 的白后——而这两个兵单独看
    **谁都不算被牵制**。"""
    b = Board("8/8/8/8/k2Pp2Q/8/8/3K4 b - d3 0 1")
    assert "e4d3" not in ucis(b)
    assert "e4e3" in ucis(b), "the ordinary push is still fine / 普通前进一步没问题"


def test_en_passant_right_expires_after_one_move():
    b = Board("4k3/8/8/8/4p3/8/3P4/4K3 w - - 0 1")
    b.push(Move.from_uci("d2d4"))
    b.push(Move.from_uci("e8d8"))                    # black declines / 黑方不吃
    b.push(Move.from_uci("e1e2"))
    assert "e4d3" not in ucis(b)


# --- promotion / 升变 ------------------------------------------------------------------

def test_promotion_offers_all_four_pieces():
    b = Board("4k3/P7/8/8/8/8/8/4K3 w - - 0 1")
    assert {"a7a8q", "a7a8r", "a7a8b", "a7a8n"} <= ucis(b)


def test_capture_promotion():
    b = Board("1r2k3/P7/8/8/8/8/8/4K3 w - - 0 1")
    assert "a7b8q" in ucis(b)
    b.push(Move.from_uci("a7b8q"))
    assert b.piece_at(ac.parse_square("b8")).piece_type == ac.QUEEN


# --- pins and check / 牵制与将军 --------------------------------------------------------

def test_a_pinned_piece_may_only_move_along_the_pin():
    """The knight on e2 shields the king from the rook on e8. It may not step aside, but
    it could capture along the same line if there were something to take.
    / e2 的马挡在王和 e8 的车之间。它不能走开，但如果线上有子可吃，它可以沿着同一条线动。"""
    b = Board("4r3/8/8/8/8/8/4N3/4K3 w - - 0 1")
    assert not any(m.startswith("e2") for m in ucis(b)), "the knight is frozen / 马被钉死"


def test_double_check_forces_the_king_to_move():
    b = Board("4k3/8/8/8/8/8/4r3/4K1n1 w - - 0 1")
    for uci in ucis(b):
        assert uci.startswith("e1"), f"{uci} is not a king move / {uci} 不是王的走法"


def test_checkmate_and_stalemate_are_told_apart():
    mate = Board("rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3")
    assert mate.is_checkmate() and not mate.is_stalemate()
    assert mate.result() == "0-1"

    stale = Board("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
    assert stale.is_stalemate() and not stale.is_checkmate()
    assert stale.result() == "1/2-1/2"


def test_king_may_not_retreat_along_the_checking_line():
    """A rook checks the king down the e-file. Stepping backwards to e1 is still check —
    the king does not block for itself. / 车沿 e 线将军。往后退到 e1 仍然在被将——王挡不住自己。"""
    b = Board("4r3/8/8/8/8/8/8/4K3 w - - 0 1")
    assert "e2e1" not in ucis(b) and "e1e2" not in ucis(b)
    assert {"d1", "f1", "d2", "f2"} & {u[2:4] for u in ucis(b)}


# --- draws / 和棋 ----------------------------------------------------------------------

def test_insufficient_material():
    assert Board("8/8/8/8/8/8/8/K6k w - - 0 1").is_insufficient_material()
    assert Board("8/8/8/8/8/8/8/KB5k w - - 0 1").is_insufficient_material()
    assert Board("8/8/8/8/8/8/8/KN5k w - - 0 1").is_insufficient_material()
    assert not Board("8/8/8/8/8/8/8/KQ5k w - - 0 1").is_insufficient_material()
    assert not Board("8/8/8/8/8/8/8/KR5k w - - 0 1").is_insufficient_material()
    assert not Board("8/8/8/8/8/8/8/KP5k w - - 0 1").is_insufficient_material()


def test_threefold_repetition():
    """Knights out and back, twice. The starting position is the first occurrence, so the
    third arrives after two full cycles. / 马出去再回来，两轮。起始局面算第一次，所以第三次出现
    是在两个完整来回之后。"""
    b = Board()
    assert b.is_repetition(3) is False
    for _ in range(2):
        for uci in ("g1f3", "g8f6", "f3g1", "f6g8"):
            b.push(Move.from_uci(uci))
    assert b.is_repetition(3) is True
    assert b.is_fivefold_repetition() is False


def test_fifty_move_counter_resets_on_pawn_moves_and_captures():
    b = Board("4k3/8/8/8/8/8/4P3/4K3 w - - 10 20")
    b.push(Move.from_uci("e1d1"))
    assert b.halfmove_clock == 11
    b.push(Move.from_uci("e8d8"))
    b.push(Move.from_uci("e2e4"))
    assert b.halfmove_clock == 0, "a pawn move resets it / 兵一动就归零"


# --- hashing / 哈希 --------------------------------------------------------------------

def test_transpositions_hash_the_same():
    """Two move orders reaching the identical position must produce the identical key,
    otherwise repetition detection would miss it.
    / 两种走法顺序到达同一个局面，必须得到同一个键，否则重复局面判定就会漏掉它。"""
    a = Board()
    for uci in ("g1f3", "g8f6", "b1c3", "b8c6"):
        a.push(Move.from_uci(uci))
    c = Board()
    for uci in ("b1c3", "b8c6", "g1f3", "g8f6"):
        c.push(Move.from_uci(uci))
    assert a.fen() == c.fen()
    assert a._hash == c._hash


def test_a_phantom_en_passant_square_does_not_change_the_key():
    """A FEN can record an en-passant square no pawn can use. Two positions differing only
    in that are the same position, and must hash the same.
    / FEN 里可以记着一个没有兵能吃的过路兵格。只在这上面有差别的两个局面其实是同一个局面，
    必须哈希成同一个键。"""
    with_ghost = Board("4k3/8/8/8/3P4/8/8/4K3 b - d3 0 1")
    without = Board("4k3/8/8/8/3P4/8/8/4K3 b - - 0 1")
    assert with_ghost._hash == without._hash


def test_hash_is_restored_by_pop():
    b = Board()
    before = b._hash
    for uci in ("e2e4", "e7e5", "g1f3", "b8c6"):
        b.push(Move.from_uci(uci))
    for _ in range(4):
        b.pop()
    assert b._hash == before == b._compute_hash()


# --- FEN -------------------------------------------------------------------------------

def test_fen_round_trip():
    for fen in (
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
        "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
        "4k3/8/8/8/4pP2/8/8/4K3 b - f3 0 9",
    ):
        assert Board(fen).fen() == fen


def test_castling_rights_are_dropped_when_the_pieces_are_not_home():
    """A FEN can claim rights it has no business claiming. / FEN 可以声称一些它根本立不住的权利。"""
    b = Board("4k3/8/8/8/8/8/8/4K2R w KQkq - 0 1")
    assert b.fen().split()[2] == "K", "only the h1 rook is actually there / 实际只有 h1 那个车在"


def test_invalid_positions_are_reported():
    missing_king = Board("4k3/8/8/8/8/8/8/8 w - - 0 1")
    assert not missing_king.is_valid()
    assert missing_king.status() & ac.Status.NO_WHITE_KING

    # A rook on e1 checks the black king down the e-file, yet it is White to move — Black
    # should have dealt with the check first, so this position could not have arisen.
    # e1 的车沿 e 线将着黑王，却轮到白走——黑方本该先应将，所以这个局面根本不可能出现。
    impossible = Board("4k3/8/8/8/8/8/8/K3R3 w - - 0 1")
    assert impossible.status() & ac.Status.OPPOSITE_CHECK
    assert not impossible.is_valid()

    assert Board("4k3/8/8/8/8/8/4P3/4K3 w - - 0 1").is_valid(), "an ordinary position / 普通局面"


# --- the API ANIMA depends on / ANIMA 依赖的那套 API ------------------------------------

def test_public_api_surface_is_complete():
    """The names ANIMA's engine and chess world import. Losing one silently is exactly the
    kind of regression this package exists to avoid.
    / ANIMA 的引擎和棋世界会 import 的那些名字。悄悄丢掉一个，正是这个包存在要避免的那类回归。"""
    required = [
        "WHITE", "BLACK", "PAWN", "KNIGHT", "BISHOP", "ROOK", "QUEEN", "KING",
        "SQUARES", "parse_square", "square_file", "square_rank",
        "Board", "Move", "Piece",
    ]
    for name in required:
        assert hasattr(ac, name), f"anima_chess.{name} is missing / 缺了 anima_chess.{name}"

    # Checked on an instance, not the class: `turn` and `move_stack` are per-position state
    # set up in `__init__`. / 在实例上查而不是在类上：`turn` 和 `move_stack` 是每个局面自己的状态、
    # 在 `__init__` 里才建立。
    board = Board()
    for name in (
        "legal_moves", "push", "pop", "piece_at", "piece_map", "turn", "move_stack", "fen",
        "is_check", "is_checkmate", "is_stalemate", "is_capture", "gives_check",
        "is_game_over", "result", "is_valid", "status", "is_insufficient_material",
        "is_seventyfive_moves", "is_fivefold_repetition",
    ):
        assert hasattr(board, name), f"Board.{name} is missing / 缺了 Board.{name}"

    # `legal_moves` must behave like python-chess's generator object, not a plain list:
    # the sim-chess world writes `if move not in board.legal_moves`.
    # `legal_moves` 的行为必须像 python-chess 那个生成器对象，而不是普通列表：
    # sim-chess 世界里写的是 `if move not in board.legal_moves`。
    assert Move.from_uci("e2e4") in board.legal_moves
    assert Move.from_uci("e2e5") not in board.legal_moves
    assert len(board.legal_moves) == 20
