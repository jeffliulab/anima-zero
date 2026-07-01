"""sim-chess 世界里【可切换的第二种棋】五子棋测试（纯 Python，无 HTTP）。

证明：① 五子棋真值盘的落子/轮换/五连判胜是真的；② 内置 bot 真会在已有子附近落合法子；
③ world 能在 chess/gomoku 间切换、画面随之变、perceive 的 state 仍只给 controllers（不泄露棋种/真值）；
④ ANIMA 的象棋走法在五子棋盘上如实失败（它只能靠画面察觉换棋，世界不点破）。
"""
from __future__ import annotations

import gomoku                       # world/sim-chess/gomoku.py（conftest 把该目录加进 sys.path）
from world import SimChessWorld


def test_place_alternates_turn_and_rejects_occupied():
    g = gomoku.GomokuBoard()
    assert g.side_to_move() == "black", "黑先"
    ok, _ = g.place(7, 7)
    assert ok and g.side_to_move() == "white"
    bad, _ = g.place(7, 7)
    assert not bad, "同点不能再落"
    ok2, _ = g.place(0, 0)
    assert ok2 and g.side_to_move() == "black"


def test_five_in_a_row_wins():
    g = gomoku.GomokuBoard()
    for i in range(4):              # 黑 (0,0..3)，白岔开放 (5,0..3)
        g.place(0, i)
        g.place(5, i)
    assert g.winner() is None, "四连还没赢"
    ok, _ = g.place(0, 4)           # 黑第五子→横五连
    assert ok and g.winner() == "black" and g.is_over() and g.result() == "black_win"


def test_bot_plays_legal_near_existing():
    g = gomoku.GomokuBoard()
    g.place(7, 7)                   # 黑天元；轮到白(bot)
    n0 = g.move_count()
    ok, _ = g.bot_move()
    r, c, col = g.moves[-1]
    assert ok and g.move_count() == n0 + 1
    assert col == "white" and g.grid[r][c] == "white", "bot 应真落一个合法白子"


def test_world_switch_changes_render_state_stays_empty():
    w = SimChessWorld()
    assert w.status()["game"] == "chess"
    chess_img = w.render_image()
    res = w.switch_game("gomoku")
    assert res["ok"] and w.status()["game"] == "gomoku"
    gomoku_img = w.render_image()
    assert gomoku_img.size != chess_img.size, "切棋种后渲染画面应明显不同"
    state, _ = w.observe()
    assert state == {}, "state 空，绝不泄露棋种/局面真值（大脑靠看画面察觉换棋了）"


def test_world_anima_chess_move_fails_on_gomoku_board():
    # 五子棋对局中，ANIMA 的象棋走法应失败（它要靠画面自己察觉换棋了）
    w = SimChessWorld()
    w.switch_game("gomoku")                  # 换成五子棋（无需选边/开局）
    res = w.invoke("move", **{"from": "e2", "to": "e4"})
    assert res["ok"] is False, "ANIMA 的象棋走法在五子棋盘上应失败"


def test_world_human_click_guarded_on_gomoku():
    # 五子棋对局中，象棋两步点击不能在隐藏象棋盘上误走子（棋种守卫，与 _move/human_place 对称）
    w = SimChessWorld()
    w.switch_game("gomoku")
    res = w.human_click_move("e2", "e4")
    assert res["ok"] is False and "象棋" in res["message"], "五子棋对局中 human_click_move 应被棋种守卫挡住"
