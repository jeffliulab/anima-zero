"""失败补救链路测试（v0.5 wave 6）：世界执行自检报失败类别 → 大脑下一拍针对性补救。

三条补救语义（对齐 v1.1「随机失败原子重试 / 系统失败先恢复再继续」）：
- grip_miss（夹空）：从失败那步原样重试（跳过已成功的前序原语）；
- place_offset（放偏）：把起点改成世界自检报告的实际落格、从那步继续（把子夹回目标）；
- 补救只对同一手棋有效（uci 对不上作废）；每次重试前 Perceive 先行（树序保证重感知）。
用内存假物理世界逐拍 tick，不 mock 行为树本身。
"""
from __future__ import annotations

import chess

import render  # world/sim-chess/render.py（conftest 加进 sys.path）
from anima.awi import ActionResult, Capabilities, Observation, ToolSpec
from anima.behavior.trees import boardgame
from anima.tools.boardgame.chess import ChessAdapter


class FlakyPhysWorld:
    """物理假世界：第一次 move 按剧本失败（带执行自检 data），之后诚实执行。裸搬不判棋规。"""

    def __init__(self, board: chess.Board, fail_once: dict):
        self.name, self.base = "flaky-phys", "fake://flaky"
        self.board = board
        self._fail_once = fail_once          # {"fail": ..., "piece_square": ...,（可选）"leave_at": sq}
        self.ops: list[tuple[str, dict]] = []

    def perceive(self) -> Observation:
        return Observation(image_png=render.to_png(render.render_board(self.board)), state={})

    def invoke(self, name, *, _on_progress=None, _should_abort=None, **cmd) -> ActionResult:
        self.ops.append((name, dict(cmd)))
        if name == "move":
            if self._fail_once is not None:
                fail, self._fail_once = self._fail_once, None
                leave_at = fail.pop("leave_at", None)
                if leave_at is not None:      # 放偏：物理后果如实保留——子真的落在偏的格上
                    f = chess.parse_square(cmd["from"])
                    p = self.board.remove_piece_at(f)
                    self.board.set_piece_at(chess.parse_square(leave_at), p)
                return ActionResult(False, "执行自检：失败", data=fail)
            f, t = chess.parse_square(cmd["from"]), chess.parse_square(cmd["to"])
            p = self.board.remove_piece_at(f)
            if p is None:
                return ActionResult(False, f"{cmd['from']} 空")
            self.board.set_piece_at(t, p)
            return ActionResult(True, "moved")
        if name == "remove":
            self.board.remove_piece_at(chess.parse_square(cmd["square"]))
            return ActionResult(True, "removed")
        return ActionResult(False, f"未知 {name}")

    def capabilities(self) -> Capabilities:
        return Capabilities(self.name, "t", [ToolSpec(n, "", {}, "tool") for n in ("move", "remove")])


def _bb(world) -> boardgame.BoardGameBlackboard:
    return boardgame.BoardGameBlackboard(
        world=world, adapter=ChessAdapter(), belief=ChessAdapter().new_state(), my_side="white",
        prims={"move", "remove"}, narrate=lambda uci, san, st: san, display_name="Chess Mode")


def test_grip_miss_retries_same_op():
    """夹空：世界报 grip_miss（子还在原格）→ 下一拍原样重试同一步，成功后信念推进一手。"""
    world = FlakyPhysWorld(chess.Board(), {"fail": "grip_miss", "piece_square": None})
    bb = _bb(world)
    tree = boardgame.build_boardgame_tree(bb)

    tree.tick_once()                                  # 第一拍：夹空失败
    assert bb.move_count == 0 and bb.act_fail == 1
    assert bb.pending_recovery is not None

    tree.tick_once()                                  # 第二拍：重试成功
    assert bb.move_count == 1
    moves = [(n, c) for n, c in world.ops if n == "move"]
    assert len(moves) == 2 and moves[0][1] == moves[1][1], "夹空应原样重试同一步"


def test_place_offset_recovers_from_actual_square():
    """放偏：子实际落在邻格（世界自检报实际落格）→ 下一拍从实际落格夹回目标格，信念推进。"""
    world = FlakyPhysWorld(chess.Board(), None)
    bb = _bb(world)
    tree = boardgame.build_boardgame_tree(bb)
    tree.tick_once()                                  # 正常走第一手（确定引擎选的 from/to）
    first = [c for n, c in world.ops if n == "move"][0]
    to = first["to"]

    # 重开一局：让引擎的这手放偏到 to 的东邻格
    offset_sq = chess.square_name(chess.square(chess.square_file(chess.parse_square(to)) + 1,
                                               chess.square_rank(chess.parse_square(to))))
    world2 = FlakyPhysWorld(chess.Board(), {"fail": "place_offset", "piece_square": offset_sq,
                                            "leave_at": offset_sq})
    bb2 = _bb(world2)
    tree2 = boardgame.build_boardgame_tree(bb2)

    tree2.tick_once()                                 # 放偏失败
    assert bb2.move_count == 0
    assert bb2.pending_recovery and bb2.pending_recovery["from"] == offset_sq

    for _ in range(4):                                # 补救可能要先经过几拍感知确认（diff 对不上→继续）
        tree2.tick_once()
        if bb2.move_count:
            break
    assert bb2.move_count == 1, "放偏后应从实际落格补救回目标格"
    recovery = [c for n, c in world2.ops if n == "move"][1]
    assert recovery["from"] == offset_sq and recovery["to"] == to


def test_recovery_invalidated_if_move_changes():
    """补救只认同一手棋：uci 对不上（引擎换了主意）→ 作废，走正常整条重来。"""
    bb = _bb(FlakyPhysWorld(chess.Board(), None))
    bb.pending_recovery = {"uci": "a2a3", "op_index": 0, "from": "b3"}
    ops = [{"op": "move", "from": "e2", "to": "e4"}]
    out = boardgame.SendMove._apply_recovery(bb, "e2e4", ops)
    assert out == ops and bb.pending_recovery is None
