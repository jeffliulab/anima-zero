"""sim-chess 简化后（v0.4）的世界行为：move 无门槛（轮次靠走子合法性天然管）、over 兜住终局/认输、
内置电脑靠 bot_side 门控、换桌/开新局。纯 Python、无 HTTP、确定性。

旧的「phase 三阶段 + controllers 席位」整套已删——防回归：world 上不该再有它们。
"""
from __future__ import annotations

import chess

from world import SimChessWorld


def test_no_phase_no_controllers():
    """防回归：简化后不再有 phase/controllers/take_seat/set_controller/start_game/seat_opponent。"""
    w = SimChessWorld()
    for attr in ("phase", "controllers", "set_controller", "take_seat", "start_game", "seat_opponent", "pause"):
        assert not hasattr(w, attr), f"简化后不该再有 {attr}"
    assert {t["name"] for t in w.capabilities()["tools"]} == {"move"}


def test_move_no_gate_turn_by_legality():
    w = SimChessWorld()
    assert w.invoke("move", **{"from": "e2", "to": "e4"})["ok"]        # 白
    assert w.invoke("move", **{"from": "e7", "to": "e5"})["ok"]        # 黑
    assert w.invoke("move", **{"from": "e2", "to": "e4"})["ok"] is False, "e2 已空 / 没轮到白"


def test_resign_sets_over_and_winner():
    w = SimChessWorld()
    r = w.resign("white")
    assert r["ok"] and w.over is True and w.result == "black"
    assert w.invoke("move", **{"from": "e2", "to": "e4"})["ok"] is False, "认输后对局结束，不能再走"


def test_bot_step_gated_by_bot_side():
    w = SimChessWorld()
    assert w.bot_step() is False, "没配内置电脑 → 不走"
    w.set_bot_side("black")
    assert w.bot_step() is False, "白回合、内置电脑执黑 → 不走"
    w.board.push(chess.Move.from_uci("e2e4"))     # 轮到黑
    assert w.bot_step() is True, "轮到内置电脑(黑) → 走"


def test_reset_is_clean_new_game():
    w = SimChessWorld()
    w.invoke("move", **{"from": "e2", "to": "e4"})
    r = w.reset()
    assert r["ok"] and w.over is False and not w.board.move_stack, "开新局 = 干净盘、清结束态"


def test_switch_game():
    w = SimChessWorld()
    r = w.switch_game("gomoku")
    assert r["ok"] and w.game == "gomoku"
    assert w.switch_game("xiangqi")["ok"] is False, "只支持 chess/gomoku/go"


def test_over_on_checkmate():
    """自然终局（愚人将 f3 e5 g4 Qh4#）→ over=True、result=black。"""
    w = SimChessWorld()
    for frm, to in [("f2", "f3"), ("e7", "e5"), ("g2", "g4"), ("d8", "h4")]:
        assert w.invoke("move", **{"from": frm, "to": to})["ok"]
    assert w.over is True and w.result == "black"
    assert w.invoke("move", **{"from": "a2", "to": "a3"})["ok"] is False, "终局后不能再走"
