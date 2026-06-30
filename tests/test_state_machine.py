"""棋桌状态机（三阶段）：阶段守卫 + 认输 + bot 只在比赛中 + 换人/换棋种只在非比赛中 +
复位/换桌清空座位 + take_seat 幂等。

world = 权威：流程规则都在世界（物理规则可硬编码）。这些是纯 Python、无 HTTP、确定性。
三阶段 = not_start / in_game / game_over（Wave 7 砍掉了全局 pause/resume）。
"""
from __future__ import annotations

import chess

from world import SimChessWorld


def _ready(white="anima", black="bot") -> SimChessWorld:
    w = SimChessWorld()
    w.set_controller("white", white)
    w.set_controller("black", black)
    return w


def test_only_three_phases_no_pause():
    """防回归：全局暂停已删——world 上不再有 pause/resume/paused_by。"""
    w = SimChessWorld()
    assert not hasattr(w, "pause") and not hasattr(w, "resume") and not hasattr(w, "paused_by")
    names = {t["name"] for t in w.capabilities()["tools"]}
    assert "pause" not in names and "resume" not in names, "pause/resume 不再是声明的工具"


def test_resign_sets_game_over_and_winner():
    w = _ready()                      # white=anima, black=bot
    w.start_game()
    r = w.resign(by="anima")          # anima(白) 认输 → 黑胜
    assert r["ok"] and w.phase == "game_over" and w.result == "black"


def test_switch_and_change_player_blocked_in_game():
    w = _ready()
    w.start_game()
    assert w.switch_game("gomoku")["ok"] is False, "比赛中不能换棋种（先复位/开新局）"
    assert w.set_controller("white", "human")["ok"] is False, "比赛中不能换人（先复位/开新局）"


def test_bot_only_steps_in_game():
    w = _ready("human", "bot")
    assert w.bot_step() is False, "未开始时 bot 不走"
    w.start_game()
    # 轮到白(human)，bot(黑)不该走
    assert w.bot_step() is False
    w.board.push(chess.Move.from_uci("e2e4"))   # 轮到黑(bot)
    assert w.bot_step() is True, "比赛中轮到 bot 才走"


def test_start_from_game_over_is_new_game():
    w = _ready()
    w.start_game()
    w.resign(by="anima")
    assert w.phase == "game_over"
    r = w.start_game()                # 开新局：从 game_over 直接重开（座位还在 → 能直接重开）
    assert r["ok"] and w.phase == "in_game"
    assert w.board.fen() == chess.STARTING_FEN, "开新局是干净盘"


# ---------- Wave 7 新增：复位/换桌清空座位 + take_seat 幂等 ----------
def test_reset_clears_seats_and_board():
    """复原棋盘后必须"没有任何 controller"（修旧 bug：以前只清盘、座位残留挡住新局就座）。"""
    w = _ready("human", "anima")        # 先有控制者
    w.start_game()
    w.board.push(chess.Move.from_uci("e2e4"))
    r = w.reset()
    assert r["ok"] and w.phase == "not_start"
    assert w.controllers == {"white": None, "black": None}, "复位=清空座位"
    assert r["controllers"] == {"white": None, "black": None}, "复位返回值也带空座位"
    assert not w.board.move_stack, "复位也清干净棋盘"


def test_switch_game_clears_seats():
    w = _ready("human", "bot")
    r = w.switch_game("gomoku")
    assert r["ok"] and w.game == "gomoku" and w.phase == "not_start"
    assert w.controllers == {"white": None, "black": None}, "换桌=彻底重来，座位也清空"


def test_take_seat_idempotent_even_in_game():
    """已坐这一席再就座 → 直接成功(noop)，不被"对弈进行中"挡掉（修 #6：脑已坐却重复 take_seat 失败）。"""
    w = SimChessWorld()
    w.take_seat("white")
    w.set_controller("black", "bot")
    w.start_game()
    assert w.phase == "in_game"
    r = w.take_seat("white")            # 已经坐着、且在比赛中
    assert r["ok"] and r.get("noop") is True, "幂等：已坐这一席再 take_seat 仍 ok"
    # 但想在比赛中坐另一个被占的席位 → 仍拒
    assert w.take_seat("black")["ok"] is False


def test_take_seat_allowed_after_game_over_once_seat_freed():
    """game_over 后复位清座 → 能重新就座开新局（#4：game-over 应当能开新局 + 落座）。"""
    w = _ready("anima", "bot")
    w.start_game(); w.resign(by="anima")
    assert w.phase == "game_over"
    w.reset()                            # 清座回 not_start
    assert w.take_seat("black")["ok"], "复位后席位空出，能重新就座"
    assert w.controllers["black"] == "anima"
