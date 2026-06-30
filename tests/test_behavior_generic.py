"""证明"通用对弈树真通用"：用一套**非象棋**的 BoardGameAdapter（一个最简计数游戏）
套上**同一棵** build_boardgame_tree，能正常走子、判轮次、判终局——

即对弈树/框架(behavior/)对棋种是真正解耦的：换棋只换工具适配器，树一行不改。
这守住"加五子棋=只写一个 tools 文件"这条架构承诺。
"""
from __future__ import annotations

from anima.awi import ActionResult, Capabilities, Observation, ToolSpec
from anima.behavior.trees import boardgame


class CountTools:
    """最简"棋种"：state 是个计数器，每"走一手"加一，到 3 就终局。不靠视觉、不靠真引擎。"""
    id = "count"
    name = "计数游戏"
    world_action = "move"
    TARGET = 3

    def new_state(self):
        return {"n": 0}

    def read_board(self, image_png):
        return {}                                  # 不靠视觉

    def read_board_detailed(self, image_png):
        return {}, set()                           # 永远"看得清"、空摆放

    def placement_of(self, state):
        return {}

    def diff_move(self, state, observed):
        return None                                # 没有对手

    def apply(self, state, move):
        state["n"] += 1

    def engine_move(self, state):
        return {"step": 1} if state["n"] < self.TARGET else None

    def is_terminal(self, state):
        over = state["n"] >= self.TARGET
        return {"over": over, "winner": "white", "reason": "done"}

    def my_turn(self, state, my_side):
        return state["n"] < self.TARGET

    def side_to_move(self, state):
        return "white"

    def to_command(self, state, move):
        return {}

    def move_uci(self, move):
        return f"step{move['step']}"

    def describe(self, state, move):
        return "一步"

    def evaluate(self, state):
        return 0


class OkWorld:
    name = "ok"
    base = "fake://ok"

    def perceive(self):
        return Observation(image_png=b"", state={})    # 非 None 即可（CountTools 不读它）

    def invoke(self, name, **cmd):
        return ActionResult(ok=True, message="ok")

    def capabilities(self):
        return Capabilities(name=self.name, version="t", tools=[ToolSpec("move", "", {}, "tool")])


def test_generic_tree_runs_with_non_chess_tools():
    adapter = CountTools()
    bb = boardgame.BoardGameBlackboard(
        world=OkWorld(), adapter=adapter, belief=adapter.new_state(), my_side="white",
        narrate=lambda u, s, st: "走了一步", display_name="计数游戏",
    )
    tree = boardgame.build_boardgame_tree(bb)

    for _ in range(CountTools.TARGET):
        tree.tick_once()
    assert bb.belief["n"] == CountTools.TARGET, "应在 N 拍内把计数走满（证明走子管线对非象棋适配器也通）"
    assert bb.move_count == CountTools.TARGET

    tree.tick_once()                               # 下一拍应判终局并收尾
    assert bb.finished and bb.exit_reason.startswith("terminal")
    assert "end" in [e["channel"] for e in bb.events]
