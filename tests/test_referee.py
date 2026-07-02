"""裁判三方对账（referee.judge）+ 观测空间投影（observed_of / OCC diff_move）单测——v0.5 wave 1。

裁判部分：三张盘（追踪层占用 / CNN 子型 / 信念期望）→ 四种结论各一测 + 退化单层。
空间部分：PIECE 空间投影与 placement_of 逐字节等价（老行为不变的硬保证）；
OCC 空间下非吃子/非升变移动唯一可辨（视觉桥能靠占用变化认对手走子的前提）。
"""
from __future__ import annotations

import chess
import pytest

from anima.tools.boardgame import referee
from anima.tools.boardgame.base import OCC, PIECE
from anima.tools.boardgame.chess import ChessAdapter

# ---- 三张盘的小样例（格号 = python-chess square int）----
E2, E4, D7, D5 = chess.E2, chess.E4, chess.D7, chess.D5


def test_judge_steady_when_all_agree_with_expected():
    occ = {E2: "w", D7: "b"}
    piece = {E2: "P", D7: "p"}
    v = referee.judge(occ, set(), piece, set(), expected_occ={E2: "w", D7: "b"})
    assert v.status == referee.STEADY


def test_judge_candidate_when_eyes_agree_but_differ_from_expected():
    occ = {E4: "w", D7: "b"}                      # 白兵已到 e4
    piece = {E4: "P", D7: "p"}
    v = referee.judge(occ, set(), piece, set(), expected_occ={E2: "w", D7: "b"})
    assert v.status == referee.CANDIDATE
    assert v.observed_for_diff == occ, "CANDIDATE 必须带上交给 diff_move 的占用盘"


def test_judge_conflict_when_eyes_disagree():
    occ = {E2: "w"}
    piece = {E4: "P"}                              # CNN 说子在 e4，追踪层说在 e2 → 矛盾
    v = referee.judge(occ, set(), piece, set(), expected_occ={E2: "w"})
    assert v.status == referee.CONFLICT
    assert v.disagree_squares == {E2, E4}


def test_judge_uncertain_when_any_eye_unsure():
    occ = {E2: "w"}
    piece = {E2: "P"}
    v = referee.judge(occ, {D5}, piece, set(), expected_occ={E2: "w"})
    assert v.status == referee.UNCERTAIN
    assert D5 in v.uncertain_squares


def test_judge_degrades_to_single_layer_when_cnn_absent():
    """CNN 未启用（None）→ 诚实退化：只拿占用盘和期望比，不假装有第二只眼。"""
    v1 = referee.judge({E2: "w"}, set(), None, set(), expected_occ={E2: "w"})
    assert v1.status == referee.STEADY
    v2 = referee.judge({E4: "w"}, set(), None, set(), expected_occ={E2: "w"})
    assert v2.status == referee.CANDIDATE


def test_uncertain_square_does_not_count_as_conflict():
    """已被标"看不清"的格，两眼不一致不算冲突（走 UNCERTAIN，不冤枉哪只眼）。"""
    v = referee.judge({E2: "w"}, {E4}, {E2: "P", E4: "P"}, set(), expected_occ={E2: "w"})
    assert v.status == referee.UNCERTAIN


# ---- 观测空间投影 ----
class _OccStubRecognizer:
    """OCC 空间识别器桩（只有空间标签；read_detailed 不会被这些测试用到）。"""
    space = OCC

    def read_detailed(self, image_png: bytes):  # pragma: no cover - 桩
        raise AssertionError("这些单测不走图像路径")


def test_piece_space_projection_is_byte_equal_to_placement_of():
    """不注入识别器（老 _vision，PIECE 空间）：observed_of == placement_of 逐字节等价——老行为不变的硬保证。"""
    a = ChessAdapter()
    assert a.space == PIECE
    b = chess.Board()
    b.push_uci("e2e4")
    assert a.observed_of(b) == a.placement_of(b)


def test_occ_projection_collapses_symbols():
    a = ChessAdapter(recognizer=_OccStubRecognizer())
    assert a.space == OCC
    occ = a.observed_of(chess.Board())
    assert occ[chess.E2] == "w" and occ[chess.E7] == "b"
    assert len(occ) == 32


@pytest.mark.parametrize("moves,next_uci", [
    ([], "e2e4"),                       # 开局兵两步
    ([], "g1f3"),                       # 开局马
    (["e2e4", "e7e5"], "f1c4"),        # 象长斜线
    (["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "f8c5"], "e1g1"),   # 短易位（两个子挪动，占用变化仍唯一）
])
def test_occ_space_noncapture_moves_uniquely_identifiable(moves, next_uci):
    """OCC 空间下非吃子/非升变移动唯一可辨：占用变化只对应一手合法棋 → diff_move 能准确认出。"""
    a = ChessAdapter(recognizer=_OccStubRecognizer())
    board = chess.Board()
    for u in moves:
        board.push_uci(u)
    after = board.copy()
    after.push_uci(next_uci)
    observed_occ = a._occ_of(after)

    mv = a.diff_move(board, observed_occ)
    assert mv is not None and mv.uci() == next_uci


def test_occ_space_promotion_is_ambiguous_returns_none():
    """OCC 空间认不出升变成什么子（e8=Q 和 e8=N 占用一样）→ diff_move 诚实返回 None（再看一眼），绝不瞎猜。"""
    a = ChessAdapter(recognizer=_OccStubRecognizer())
    board = chess.Board("4k3/P7/8/8/8/8/8/4K3 w - - 0 1")   # 白兵 a7 待升变
    after = board.copy()
    after.push_uci("a7a8q")
    observed_occ = a._occ_of(after)

    assert a.diff_move(board, observed_occ) is None
