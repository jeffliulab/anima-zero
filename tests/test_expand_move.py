"""ChessAdapter.expand_move —— 把一手逻辑棋拆成「物理原语序列」，且按世界能力（有没有 remove/place）拆。

这是新通用棋类框架的核心：同一个适配器，数据世界（只有 move，如 sim-chess）和物理世界
（move+remove+place，如 gazebo-chess）都能驱动——差别只在 expand_move 读到的原语集，框架零特判。

用 __new__ 造适配器、不加载引擎（expand_move / seed 不需要引擎）。
"""
from __future__ import annotations

import chess

from anima.tools.boardgame.chess import ChessAdapter

DATA = {"move"}                    # 数据世界（sim-chess）：数据层一步吞吃子/易位/升变
PHYS = {"move", "remove", "place"}  # 物理世界（gazebo-chess）：真夹真放，得逐个拆


def _adapter() -> ChessAdapter:
    return ChessAdapter.__new__(ChessAdapter)   # 跳过引擎加载


def _expand(fen: str, uci: str, prims: set) -> list[dict]:
    a, b = _adapter(), chess.Board(fen)
    mv = chess.Move.from_uci(uci)
    assert mv in b.legal_moves, f"测试自身写错：{uci} 在 {fen} 不合法"
    return a.expand_move(b, mv, prims)


def test_normal_move_is_single_move_everywhere():
    for prims in (DATA, PHYS):
        assert _expand(chess.STARTING_FEN, "e2e4", prims) == [
            {"op": "move", "from": "e2", "to": "e4", "piece": "P"}]


def test_data_world_absorbs_everything_in_one_move():
    # 数据世界：吃子/易位/过路兵/升变全是一步 move（世界数据层自己吞）
    cap = _expand("rnbqkbnr/pppp1ppp/8/4p3/3P4/8/PPP1PPPP/RNBQKBNR w KQkq - 0 2", "d4e5", DATA)
    assert cap == [{"op": "move", "from": "d4", "to": "e5", "piece": "P"}]
    castle = _expand("rnbqk2r/pppp1ppp/5n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4", "e1g1", DATA)
    assert castle == [{"op": "move", "from": "e1", "to": "g1", "piece": "K"}]
    promo = _expand("8/P6k/8/8/8/8/7K/8 w - - 0 1", "a7a8q", DATA)
    assert promo == [{"op": "move", "from": "a7", "to": "a8", "piece": "P", "promotion": "q"}]


def test_physical_capture_removes_target_then_moves():
    ops = _expand("rnbqkbnr/pppp1ppp/8/4p3/3P4/8/PPP1PPPP/RNBQKBNR w KQkq - 0 2", "d4e5", PHYS)
    assert ops == [{"op": "remove", "square": "e5"},
                   {"op": "move", "from": "d4", "to": "e5", "piece": "P"}]


def test_physical_en_passant_removes_the_bystander_pawn():
    # 白 e5 兵吃过路兵到 d6：被吃的黑兵在 d5（不在落点 d6）
    ops = _expand("rnbqkbnr/ppp1pppp/8/3pP3/8/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 3", "e5d6", PHYS)
    assert ops == [{"op": "remove", "square": "d5"},
                   {"op": "move", "from": "e5", "to": "d6", "piece": "P"}]


def test_physical_castling_moves_king_then_rook():
    ks = _expand("rnbqk2r/pppp1ppp/5n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4", "e1g1", PHYS)
    assert ks == [{"op": "move", "from": "e1", "to": "g1", "piece": "K"},
                  {"op": "move", "from": "h1", "to": "f1", "piece": "R"}]
    qs = _expand("r3kbnr/pppqpppp/2npb3/8/3P4/2NQB3/PPP1PPPP/R3KBNR w KQkq - 6 5", "e1c1", PHYS)
    assert qs == [{"op": "move", "from": "e1", "to": "c1", "piece": "K"},
                  {"op": "move", "from": "a1", "to": "d1", "piece": "R"}]


def test_physical_promotion_push_moves_then_swaps_piece():
    ops = _expand("8/P6k/8/8/8/8/7K/8 w - - 0 1", "a7a8q", PHYS)
    assert ops == [{"op": "move", "from": "a7", "to": "a8", "piece": "P"},
                   {"op": "remove", "square": "a8"},
                   {"op": "place", "square": "a8", "piece": "Q"}]


def test_physical_promotion_capture_full_sequence():
    # 吃子升变：先移走被吃子 → 兵走上去 → 移走兵 → 摆上后
    ops = _expand("1n5k/P7/8/8/8/8/7K/8 w - - 0 1", "a7b8q", PHYS)
    assert ops == [{"op": "remove", "square": "b8"},
                   {"op": "move", "from": "a7", "to": "b8", "piece": "P"},
                   {"op": "remove", "square": "b8"},
                   {"op": "place", "square": "b8", "piece": "Q"}]


def test_physical_promotion_without_place_degrades_to_flag():
    # 物理世界只有 remove、没有 place → 升变退化成给 move 带 promotion 标记（世界自换子）
    ops = _expand("8/P6k/8/8/8/8/7K/8 w - - 0 1", "a7a8q", {"move", "remove"})
    assert ops == [{"op": "move", "from": "a7", "to": "a8", "piece": "P", "promotion": "q"}]


def test_seed_from_vision_reconstructs_opening_board():
    a = _adapter()
    ref = chess.Board()
    a.read_board = lambda _img: {sq: p.symbol() for sq, p in ref.piece_map().items()}
    seeded = a.seed_from_vision(b"fake-png", "white")
    assert seeded.board_fen() == ref.board_fen()
    assert seeded.turn == chess.WHITE
    assert seeded.castling_xfen() == "KQkq"
