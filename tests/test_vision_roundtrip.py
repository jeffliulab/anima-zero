"""视觉 round-trip 测试：世界渲染 → 大脑视觉读回，应 100% 还原棋子摆放。

这正是 chess_vision.py 注释里一直声称、却从未真正存在的那个测试——现在补上。
它守住"render.py(世界外观) 与 chess_vision(大脑视觉) 两侧逐像素一致"这条不变量：
一旦有人改了任一侧的外观常量/画法、两边对不上，这个测试立刻红。

注：read_board 只认棋子摆放（不含轮次/易位权——画面里本就没有），所以对照的真值
也用 placement（chess_vision.placement_of_board），而不是整盘 FEN。
"""
from __future__ import annotations

import chess
import pytest

import render  # world/sim-chess/render.py（由 conftest 加进 sys.path）
from anima.tools.boardgame import _vision as chess_vision


def _board_after(uci_moves: list[str]) -> chess.Board:
    b = chess.Board()
    for m in uci_moves:
        b.push_uci(m)
    return b


# 一组覆盖面广的局面：开局、发展、王翼易位、可吃过路兵、升变后、残局
CASES = {
    "startpos": [],
    "open_e4e5_nf3": ["e2e4", "e7e5", "g1f3"],
    "kingside_castle": ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "f8c5", "e1g1"],
    "en_passant_avail": ["e2e4", "a7a6", "e4e5", "d7d5"],  # 此刻白可 e5xd6 过路兵
    "promoted_queen": ["a2a4", "b7b5", "a4b5", "a7a6", "b5a6", "b8c6", "a6a7", "a8b8", "a7a8q"],
    "endgame_kq_vs_k": None,  # 见下，用 FEN 直接摆
}


@pytest.mark.parametrize("name", list(CASES))
def test_render_then_read_is_lossless(name):
    if name == "endgame_kq_vs_k":
        board = chess.Board("8/8/8/4k3/8/8/4Q3/4K3 w - - 0 1")
    else:
        board = _board_after(CASES[name])

    png = render.to_png(render.render_board(board))
    observed, uncertain = chess_vision.read_board_detailed(png)
    truth = chess_vision.placement_of_board(board)

    assert observed == truth, (
        f"[{name}] 视觉读回与真值不一致：渲染↔视觉外观规格已不对齐。\n"
        f"  缺/错的格子: { {sq: (truth.get(sq), observed.get(sq)) for sq in set(truth)|set(observed) if truth.get(sq)!=observed.get(sq)} }"
    )
    # 干净合成图上，Lowe 比值检验不该把任何格判成"看不清"（否则阈值过紧/外观漂移）
    assert not uncertain, f"[{name}] 合成图不该有'看不清'的格子，却有 {len(uncertain)} 个：阈值或外观对齐有问题"


def test_selection_highlight_is_opt_in_and_non_corrupting():
    """人类选子高亮圈：① 默认不画（render 不传/传 None 逐字节一致→视觉完全不受影响）；
    ② 画了之后图确实变了；③ 对大脑是"优雅的视觉扰动"——除被圈那一格外其余照常读对，
    被圈格即便读得不一样也必须被标记为'看不清'（绝不被静默误读成别的子）。"""
    board = chess.Board()
    assert render.to_png(render.render_board(board)) == render.to_png(render.render_board(board, None)), \
        "默认 None 必须与不传参逐字节一致（否则视觉 round-trip 会被动到）"
    circled = render.to_png(render.render_board(board, "e2"))
    assert circled != render.to_png(render.render_board(board)), "选了子应在画面上出现高亮圈"

    observed, uncertain = chess_vision.read_board_detailed(circled)
    truth = chess_vision.placement_of_board(board)
    diff = [k for k in set(truth) | set(observed) if truth.get(k) != observed.get(k)]
    assert len(diff) <= 1, f"选子圈最多只该影响被圈那一格，却影响了 {diff}"
    if diff:
        assert diff[0] in uncertain, "被圈格若读得不一样，必须被判'看不清'（优雅降级），不能静默误读成别的子"


def test_empty_board_reads_empty():
    board = chess.Board.empty()
    png = render.to_png(render.render_board(board))
    assert chess_vision.read_board(png) == {}
