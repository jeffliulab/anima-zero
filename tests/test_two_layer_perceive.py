"""双层视觉桥 × 对弈树 Perceive 的集成测试（v0.5 wave 5 接线）。

不走真图像：给适配器注入「脚本化识别器」（每拍按剧本吐占用盘），第二只眼同理吐子型盘——
验证的是 Perceive 的裁判路径本身：三方一致才推进、冲突/看不清走 RUNNING（再看一眼）、
CANDIDATE 走多帧确认 + diff_move + 子型级交叉核对。逐拍手动 tick，确定性、不依赖时间。
"""
from __future__ import annotations

import chess
from py_trees.common import Status

from anima import config
from anima.awi import ActionResult, Capabilities, Observation, ToolSpec
from anima.behavior.trees import boardgame
from anima.tools.boardgame.base import OCC, PIECE
from anima.tools.boardgame.chess import ChessAdapter


class DummyWorld:
    """只提供画面字节的假世界（内容无所谓——识别器是脚本化的）。"""
    name, base = "dummy-phys", "fake://phys"

    def perceive(self) -> Observation:
        return Observation(image_png=b"png", state={})

    def invoke(self, name, *, _on_progress=None, _should_abort=None, **cmd) -> ActionResult:
        return ActionResult(True, "ok")

    def capabilities(self) -> Capabilities:
        return Capabilities(self.name, "t", [ToolSpec(n, "", {}, "tool") for n in ("move", "remove", "place")])


class ScriptedEye:
    """脚本化识别器：每次 read_detailed 按顺序吐 (placement, uncertain)，播完停在最后一帧。"""

    def __init__(self, space: str, frames: list[tuple[dict, set]]):
        self.space = space
        self._frames = list(frames)

    def read_detailed(self, image_png: bytes):
        if len(self._frames) > 1:
            return self._frames.pop(0)
        return self._frames[0]


def occ_of(board: chess.Board) -> dict:
    return {sq: ("w" if p.color else "b") for sq, p in board.piece_map().items()}


def piece_of(board: chess.Board) -> dict:
    return {sq: p.symbol() for sq, p in board.piece_map().items()}


def _bb(occ_frames, piece_frames, belief: chess.Board, my_side="black"):
    """my_side 默认黑：第一拍轮到白（对手），树只感知不落子——聚焦测 Perceive。"""
    adapter = ChessAdapter(recognizer=ScriptedEye(OCC, occ_frames))
    eye2 = ScriptedEye(PIECE, piece_frames) if piece_frames is not None else None
    return boardgame.BoardGameBlackboard(
        world=DummyWorld(), adapter=adapter, second_eye=eye2, belief=belief, my_side=my_side,
        prims={"move"}, narrate=lambda uci, san, st: san, display_name="Chess Mode")


def test_steady_when_all_three_agree():
    b = chess.Board()
    bb = _bb([(occ_of(b), set())], [(piece_of(b), set())], b.copy())
    tree = boardgame.build_boardgame_tree(bb)
    tree.tick_once()
    assert bb.running_streak == 0 and not bb.finished
    assert not any(e["channel"] == "opponent" for e in bb.events)


def test_conflict_between_eyes_holds_belief():
    """两眼矛盾（CNN 说 e4 有子、追踪层说没有）→ 再看一眼，绝不推进信念。"""
    b = chess.Board()
    after = b.copy(); after.push_uci("e2e4")
    bb = _bb([(occ_of(b), set())], [(piece_of(after), set())], b.copy())
    tree = boardgame.build_boardgame_tree(bb)
    for _ in range(3):
        tree.tick_once()
    assert bb.belief.fen() == chess.Board().fen(), "冲突时信念绝不能动"
    assert bb.running_streak >= 1


def test_candidate_confirmed_then_diff_move_applies():
    """两眼一致地看到对手走了 e2e4 → 多帧确认后 diff_move 采信、信念推进、emit opponent。"""
    b = chess.Board()
    after = b.copy(); after.push_uci("e2e4")
    frames = config.VISION_CONFIRM_FRAMES + 1
    bb = _bb([(occ_of(after), set())] * frames, [(piece_of(after), set())] * frames, b.copy())
    tree = boardgame.build_boardgame_tree(bb)
    for _ in range(frames):
        tree.tick_once()
    assert any(e["channel"] == "opponent" and e.get("uci") == "e2e4" for e in bb.events)
    assert bb.belief.piece_at(chess.E4) is not None


def test_strict_piece_check_blocks_mismatched_move():
    """占用级两眼一致、diff_move 认出 e2e4，但 CNN 的【子型】和这手对不上 → strict 核对拦下、信念不动。
    （口子选"无关格子型说错"：a1 车被 CNN 认成后——占用同为 'w' 所以裁判互检过得去，
    恰好落在子型级核对的职责范围；若是占用级不一致，裁判早就 CONFLICT 了轮不到 strict。）"""
    b = chess.Board()
    after = b.copy(); after.push_uci("e2e4")
    frames = config.VISION_CONFIRM_FRAMES + 2
    wrong_far = piece_of(after); wrong_far[chess.A1] = "Q"          # a1 车被 CNN 认成后（占用同为 'w'）
    bb = _bb([(occ_of(after), set())] * frames, [(wrong_far, set())] * frames, b.copy())
    tree = boardgame.build_boardgame_tree(bb)
    for _ in range(frames):
        tree.tick_once()
    assert not any(e["channel"] == "opponent" for e in bb.events), "子型核对不过就不该采信这手"
    assert bb.belief.fen() == chess.Board().fen()


def test_cnn_absent_degrades_to_single_layer():
    """没有第二只眼（权重缺失）→ 单层照常工作：占用一致仍能认出走子（诚实降级不阻塞）。"""
    b = chess.Board()
    after = b.copy(); after.push_uci("g1f3")
    frames = config.VISION_CONFIRM_FRAMES + 1
    bb = _bb([(occ_of(after), set())] * frames, None, b.copy())
    tree = boardgame.build_boardgame_tree(bb)
    for _ in range(frames):
        tree.tick_once()
    assert any(e["channel"] == "opponent" and e.get("uci") == "g1f3" for e in bb.events)
