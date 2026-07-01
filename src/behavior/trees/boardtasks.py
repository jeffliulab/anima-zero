"""record / setup —— 两个「棋盘子任务」的行为树，和对弈(play, 见 boardgame.py)同属一个「大下棋 skill 家族」，
由用户用聊天挑着组合（"先记录一下这盘棋" → record；"按开局摆好" → setup；"你执白开下" → play）。

- **record**：读一次当前棋盘画面 → 用视觉构造信念局面 → 汇报给人看。一拍即完（半路接手/查看局面用）。
- **setup** ：把一个目标局面「摆出来」= 一串 `place` 物理原语（从备用子区取子摆到格），每拍摆一个子。需世界支持 place。

两者复用对弈黑板（BoardGameBlackboard）的 world/adapter/belief/prims/emit/finished 字段——同一套底座，
不同的叶子逻辑。棋种差异全在注入的 adapter 里（seed_from_vision / 目标局面），本文件棋种无关。
"""
from __future__ import annotations

from typing import Any, Optional

import chess
from py_trees.behaviour import Behaviour
from py_trees.common import Status

from .boardgame import BoardGameBlackboard
from ..runner import BehaviorRunner
from ...world_client import RemoteWorld
from ... import config


class RecordBoard(Behaviour):
    """一拍：读画面 → adapter.seed_from_vision 构造信念局面 → 汇报（emit record）。读不到就如实说、收尾。"""

    def __init__(self, bb: BoardGameBlackboard):
        super().__init__("record_board")
        self.bb = bb

    def update(self) -> Status:
        c = self.bb
        try:
            obs = c.world.perceive()
        except Exception as e:  # noqa: BLE001
            c.emit("fail", f"读盘失败：{type(e).__name__}")
            c.finished = True
            return Status.SUCCESS
        if obs.image_png is None:
            c.emit("fail", "世界给不出画面，读不了盘。")
            c.finished = True
            return Status.SUCCESS
        side = c.my_side if c.my_side in ("white", "black") else "white"
        try:
            c.belief = c.adapter.seed_from_vision(obs.image_png, side)
        except Exception as e:  # noqa: BLE001
            c.emit("fail", f"识别棋盘失败：{type(e).__name__}")
            c.finished = True
            return Status.SUCCESS
        n = len(c.belief.piece_map()) if hasattr(c.belief, "piece_map") else 0
        fen = c.belief.fen() if hasattr(c.belief, "fen") else str(c.belief)
        c.record_fen = fen
        c.emit("record", f"记录了当前棋盘（识别到 {n} 个子）：{fen}", fen=fen)
        c.finished = True
        return Status.SUCCESS


class SetupBoard(Behaviour):
    """把 target 局面一子一子摆出来：每拍 place 一个还没摆的子。摆完收尾。

    target = {square: 符号}（square 可为 0..63 或 'e2'）。默认标准开局。世界得支持 place（物理世界）。
    """

    def __init__(self, bb: BoardGameBlackboard, target: dict):
        super().__init__("setup_board")
        self.bb = bb
        self.target = target
        self._todo: Optional[list[tuple[str, str]]] = None

    def update(self) -> Status:
        c = self.bb
        if "place" not in c.prims:
            c.emit("fail", "这个世界不支持 place（摆子），没法摆盘。")
            c.finished = True
            return Status.SUCCESS
        if self._todo is None:
            self._todo = [((chess.square_name(sq) if isinstance(sq, int) else str(sq)), sym)
                          for sq, sym in self.target.items()]
            self._total = len(self._todo)
        if not self._todo:
            c.emit("end", f"摆盘完成，共摆了 {self._total} 个子。")
            c.finished = True
            return Status.SUCCESS
        square, sym = self._todo.pop(0)
        res = c.world.invoke("place", square=square, piece=sym)
        if res.ok:
            c.emit("setup", f"摆好 {sym}@{square}（还剩 {len(self._todo)}）", square=square, piece=sym)
        else:
            c.emit("fail", f"摆 {sym}@{square} 没成：{res.message}")
        return Status.RUNNING


def _game_world(shared_world):
    return RemoteWorld(getattr(shared_world, "name", "world"),
                       getattr(shared_world, "base", ""), timeout=config.GAME_WORLD_TIMEOUT)


def _prims_of(shared_world) -> set:
    try:
        return {t.name for t in shared_world.capabilities().tools}
    except Exception:  # noqa: BLE001
        return {"move"}


def start_record(shared_world, adapter, my_side: str = "white",
                 display_name: str = "Record Board") -> BehaviorRunner:
    gw = _game_world(shared_world)
    bb = BoardGameBlackboard(world=gw, adapter=adapter, belief=adapter.new_state(),
                             my_side=my_side, prims=_prims_of(shared_world), display_name=display_name)
    bb.emit("start", f"进入 {display_name}，读一眼当前棋盘。")
    return BehaviorRunner(bb, RecordBoard(bb), teardown=gw.close)


def default_setup_target(adapter) -> dict:
    """标准开局的目标摆放 {square_name: 符号}——从适配器的开局局面派生（棋种自带），不写死。"""
    state = adapter.new_state()
    if hasattr(state, "piece_map"):
        return {chess.square_name(sq): p.symbol() for sq, p in state.piece_map().items()}
    return {}


def start_setup(shared_world, adapter, target: Optional[dict] = None,
                display_name: str = "Setup Board") -> BehaviorRunner:
    gw = _game_world(shared_world)
    bb = BoardGameBlackboard(world=gw, adapter=adapter, belief=adapter.new_state(),
                             my_side="white", prims=_prims_of(shared_world), display_name=display_name)
    tgt = target if target is not None else default_setup_target(adapter)
    bb.emit("start", f"进入 {display_name}，把棋子摆到盘上（{len(tgt)} 个）。")
    return BehaviorRunner(bb, SetupBoard(bb, tgt), teardown=gw.close)
