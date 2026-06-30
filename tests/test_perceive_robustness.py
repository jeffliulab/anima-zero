"""感知健壮性测试（P1）：验证两条审计重点修复——

1. 世界断线时**不再静默空转**：perceive 连续失败攒到上限 → 判 world_unreachable 退出 + 可见 fail 事件。
2. 视觉"看不清"时**不硬猜**：返回 RUNNING(再看一拍)、不决策；长时间看不清 → 发可见的"卡住"报警。
"""
from __future__ import annotations

from anima import config
from anima.behavior.trees import boardgame
from anima.tools.boardgame.chess import ChessAdapter


class BlindWorld:
    """perceive 永远抛异常（模拟世界离线/断线）。"""
    name = "blind"
    base = "fake://blind"

    def perceive(self):
        raise ConnectionError("world down")


class FuzzyTools:
    """视觉永远"看不清"（uncertain 非空）的最简工具，用来测三态里的 RUNNING 分支。"""
    id = "fuzzy"
    name = "看不清"

    def new_state(self):
        return object()

    def read_board_detailed(self, image_png):
        return {}, {0, 1, 2}                       # 总有 3 格看不清

    def read_board(self, image_png):
        return {}


class ImgWorld:
    name = "img"
    base = "fake://img"

    def perceive(self):
        from anima.awi import Observation
        return Observation(image_png=b"not-empty", state={})


def _channels(bb):
    return [e["channel"] for e in bb.events]


def test_world_down_exits_not_silent_spin():
    bb = boardgame.BoardGameBlackboard(
        world=BlindWorld(), adapter=ChessAdapter(), belief=ChessAdapter().new_state(),
        my_side="white", narrate=lambda *a: "", display_name="Chess",
    )
    tree = boardgame.build_boardgame_tree(bb)

    for _ in range(config.GAME_PERCEIVE_MAX_FAIL + 1):
        tree.tick_once()

    assert bb.finished, "世界连续断线到上限后应判定退出，而不是无声空转"
    assert bb.exit_reason == "world_unreachable"
    assert bb.perceive_fail > config.GAME_PERCEIVE_MAX_FAIL
    assert "fail" in _channels(bb), "每次感知失败应 emit 可见事件"
    assert "end" in _channels(bb)


def test_uncertain_vision_returns_running_and_warns():
    bb = boardgame.BoardGameBlackboard(
        world=ImgWorld(), adapter=FuzzyTools(), belief=FuzzyTools().new_state(),
        my_side="white", narrate=lambda *a: "", display_name="Fuzzy",
    )
    tree = boardgame.build_boardgame_tree(bb)

    for _ in range(config.GAME_PERCEIVE_MAX_FAIL):
        tree.tick_once()

    assert not bb.finished, "看不清不该把对局判死——只是再看一眼"
    assert bb.move_count == 0, "看不清时绝不决策/走子"
    assert "vision" in _channels(bb), "应有一次'看不清，再看'的可见提示"
    assert "stuck" in _channels(bb), "长时间看不清应发可见的'卡住'报警(不静默)"
    assert bb.perceive_fail == 0, "'看不清'属视觉不确定、不算世界异常，不计 perceive_fail"
