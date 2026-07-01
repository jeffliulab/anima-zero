"""record / setup 两个棋盘子任务行为的单测（不起 HTTP、不起后台线程，直接 tick 叶子）。

record：读渲染盘 → seed_from_vision 构造信念（render→read round-trip 100%，见 test_vision_roundtrip）。
setup ：物理世界(有 place)把目标局面逐子 place 出来；数据世界(无 place)如实拒绝。
"""
from __future__ import annotations

import chess

import render  # world/sim-chess/render.py（conftest 加进 sys.path）
from anima.awi import ActionResult, Capabilities, Observation, ToolSpec
from anima.behavior.trees import boardtasks
from anima.behavior.trees.boardgame import BoardGameBlackboard
from anima.tools.boardgame.chess import ChessAdapter


class RenderWorld:
    name, base = "rw", "fake://rw"

    def __init__(self, board: chess.Board):
        self.board = board

    def perceive(self) -> Observation:
        return Observation(image_png=render.to_png(render.render_board(self.board)), state={})

    def invoke(self, name, **cmd) -> ActionResult:
        return ActionResult(ok=True, message="ok")

    def capabilities(self) -> Capabilities:
        return Capabilities("rw", "t", [ToolSpec("move", "", {}, "tool")])

    def close(self):
        pass


class PlaceWorld:
    name, base = "pw", "fake://pw"

    def __init__(self):
        self.placed: list[tuple[str, str]] = []

    def perceive(self) -> Observation:
        return Observation(image_png=b"x", state={})

    def invoke(self, name, **cmd) -> ActionResult:
        if name == "place":
            self.placed.append((cmd["square"], cmd["piece"]))
            return ActionResult(ok=True, message="ok")
        return ActionResult(ok=False, message=f"未知 {name}")

    def capabilities(self) -> Capabilities:
        return Capabilities("pw", "t", [ToolSpec(x, "", {}, "tool") for x in ("move", "remove", "place")])

    def close(self):
        pass


def _bb(world, prims) -> BoardGameBlackboard:
    a = ChessAdapter()
    return BoardGameBlackboard(world=world, adapter=a, belief=a.new_state(), my_side="white", prims=set(prims))


def _channels(bb):
    return [e["channel"] for e in bb.events]


def test_record_seeds_belief_from_current_board():
    board = chess.Board()
    bb = _bb(RenderWorld(board), {"move"})
    boardtasks.RecordBoard(bb).update()
    assert bb.finished
    assert bb.belief.board_fen() == board.board_fen(), "读盘构造的信念应等于当前局面"
    assert "record" in _channels(bb)


def test_record_reports_failure_when_no_image():
    world = RenderWorld(chess.Board())
    world.perceive = lambda: Observation(image_png=None, state={})
    bb = _bb(world, {"move"})
    boardtasks.RecordBoard(bb).update()
    assert bb.finished and "fail" in _channels(bb)


def test_setup_places_target_pieces_in_full():
    world = PlaceWorld()
    bb = _bb(world, {"move", "remove", "place"})
    target = {"e1": "K", "e8": "k", "a1": "R"}
    node = boardtasks.SetupBoard(bb, target)
    for _ in range(len(target) + 3):
        if bb.finished:
            break
        node.update()
    assert bb.finished
    assert set(world.placed) == {("e1", "K"), ("e8", "k"), ("a1", "R")}
    assert "end" in _channels(bb)


def test_setup_refuses_without_place_capability():
    world = PlaceWorld()
    bb = _bb(world, {"move"})                     # 没有 place
    boardtasks.SetupBoard(bb, {"e1": "K"}).update()
    assert bb.finished and "fail" in _channels(bb)
    assert world.placed == [], "没 place 能力就不该发 place"


def test_default_setup_target_is_standard_opening():
    tgt = boardtasks.default_setup_target(ChessAdapter())
    assert len(tgt) == 32 and tgt["e1"] == "K" and tgt["e8"] == "k" and tgt["d1"] == "Q"
