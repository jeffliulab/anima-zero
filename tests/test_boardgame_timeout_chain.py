"""超时/失联链路测试（v0.5 wave 0）：把 v0.4 踩过的雷变成回归网。

链路：世界调用等不到结果（RemoteWorld 把 LivenessTimeout 等映射成 ok=False 的诚实 ActionResult）
→ SendMove 记 act_fail、emit "fail"、下拍重试 → 连续失败超 GAME_MAX_FAIL → 树以 too_many_fails
诚实退出。全程不 mock 行为树本身，用内存假世界确定性逐拍 tick。
"""
from __future__ import annotations

import chess

import render  # world/sim-chess/render.py（conftest 加进 sys.path）
from anima import config
from anima.awi import ActionResult, Capabilities, Observation, ToolSpec
from anima.behavior.trees import boardgame
from anima.tools.boardgame.chess import ChessAdapter


class UnreachableActWorld:
    """感知正常、但每次动作都「失联」的假世界——模拟世界卡死/断线时 RemoteWorld 的对外表现
    （RemoteWorld 把 LivenessTimeout 映射成 ok=False + 人话消息，绝不抛异常上树）。"""

    def __init__(self, board: chess.Board | None = None):
        self.name = "fake-dead"
        self.base = "fake://dead"
        self.board = board or chess.Board()
        self.invoke_calls = 0

    def perceive(self) -> Observation:
        return Observation(image_png=render.to_png(render.render_board(self.board)), state={})

    def invoke(self, name, *, _on_progress=None, _should_abort=None, **cmd) -> ActionResult:
        self.invoke_calls += 1
        return ActionResult(False, f"世界失联：{config.WORLD_LIVENESS_TIMEOUT:g}s 无生命迹象")

    def capabilities(self) -> Capabilities:
        return Capabilities(self.name, "t", [ToolSpec("move", "", {}, "tool")])


def _bb(world) -> boardgame.BoardGameBlackboard:
    return boardgame.BoardGameBlackboard(
        world=world, adapter=ChessAdapter(), belief=ChessAdapter().new_state(), my_side="white",
        prims={"move"}, narrate=lambda uci, san, st: f"走了 {san}", display_name="Chess Mode")


def test_sendmove_records_failure_and_retries_next_tick():
    """单次失联：SendMove 记一次 act_fail + emit fail，信念不推进，下拍还会再试。"""
    world = UnreachableActWorld()
    bb = _bb(world)
    tree = boardgame.build_boardgame_tree(bb)

    tree.tick_once()
    assert bb.act_fail == 1
    assert bb.move_count == 0, "没走成就绝不推进信念"
    assert any(e["channel"] == "fail" and "失联" in e["text"] for e in bb.events)

    tree.tick_once()
    assert world.invoke_calls == 2, "下一拍应重试，而不是放弃"


def test_tree_exits_after_max_fail():
    """连续失联超上限 → too_many_fails 诚实退出（不无限空转、不假装在下棋）。"""
    world = UnreachableActWorld()
    bb = _bb(world)
    tree = boardgame.build_boardgame_tree(bb)

    for _ in range(config.GAME_MAX_FAIL + 2):
        tree.tick_once()

    assert bb.exit_reason == "too_many_fails"
    assert bb.finished
    assert any(e["channel"] == "end" for e in bb.events)


def test_progress_events_reach_event_stream():
    """世界报进度 → SendMove 转发到事件流（channel="progress"），用户看得到"臂在干什么"。"""

    class ProgressWorld(UnreachableActWorld):
        def invoke(self, name, *, _on_progress=None, _should_abort=None, **cmd) -> ActionResult:
            if _on_progress is not None:
                _on_progress("已夹取，正在移向 e4", 0.5, 1.0)
            # 走成：裸搬信念期望的那一步（数据世界形态）
            uci = f"{cmd['from']}{cmd['to']}{cmd.get('promotion', '')}"
            self.board.push(chess.Move.from_uci(uci))
            return ActionResult(True, "ok")

    world = ProgressWorld()
    bb = _bb(world)
    tree = boardgame.build_boardgame_tree(bb)
    tree.tick_once()

    progress = [e for e in bb.events if e["channel"] == "progress"]
    assert progress and "已夹取" in progress[0]["text"]
    assert bb.move_count == 1
