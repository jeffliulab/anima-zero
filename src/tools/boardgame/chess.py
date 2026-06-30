"""象棋工具适配器（ChessAdapter）—— ANIMA 下国际象棋的整套原子能力：
视觉(read_board) + 引擎(engine_move) + 规则(python-chess) + 形势评分(evaluate)。

**解耦**：只有这个文件 import 你的引擎（`3-anima-chess-engine/chess/engine.py`，跨仓非包，用 importlib
按路径加载）。升级 ANIMA 棋力 = 只换它背后的引擎，行为树/skill/别的棋一行不动。**不改引擎源码，只在外面包。**

state = 一个 python-chess Board（ANIMA 期望的局面）；世界才是唯一真值，每拍用视觉校准。
"""
from __future__ import annotations

import importlib.util
from typing import Optional

import chess

from ... import config
from . import _vision
from .base import register_adapter


def _load_engine():
    # 路径从仓库结构派生（或 env 覆盖），无绝对路径硬编码
    spec = importlib.util.spec_from_file_location("anima_chess_engine", config.chess_engine_path())
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ChessAdapter:
    id = "chess"
    name = "国际象棋"
    world_action = "move"    # 这盘棋需要世界提供的落子能力（用于能力判断，不在别处写死）

    def __init__(self, depth: int | None = None, time_limit: float | None = None) -> None:
        self._engine = _load_engine()
        depth = depth if depth is not None else config.CHESS_DEPTH
        time_limit = time_limit if time_limit is not None else config.CHESS_TIME
        self.ai = self._engine.AI(depth=depth, time_limit=time_limit)

    def new_state(self) -> chess.Board:
        return chess.Board()

    # ---- 视觉 ----
    def read_board(self, image_png: bytes) -> dict:
        return _vision.read_board(image_png)

    def read_board_detailed(self, image_png: bytes) -> tuple[dict, set]:
        return _vision.read_board_detailed(image_png)

    def placement_of(self, state: chess.Board) -> dict:
        return _vision.placement_of_board(state)

    # ---- 轮次判断：观测摆放和 state 比，认出对手走的那一手 ----
    def diff_move(self, state: chess.Board, observed: dict) -> Optional[chess.Move]:
        if observed == self.placement_of(state):
            return None                                   # 没变 → 对手还没走
        matches = []                                      # 找出所有能产生 observed 的合法着法
        for mv in state.legal_moves:
            state.push(mv)
            same = self.placement_of(state) == observed
            state.pop()
            if same:
                matches.append(mv)
        # 恰好一手 → 采信；0 手=对不上(视觉异常)；>1 手=歧义(罕见，理论存在)——都返回 None，
        # 交上层"跳过本拍、下拍再看"，绝不静默取第一个（升变 Q/R/B/N 摆放符号不同、本就不歧义）。
        return matches[0] if len(matches) == 1 else None

    def apply(self, state: chess.Board, move: chess.Move) -> None:
        state.push(move)

    # ---- 引擎出手（ANIMA 自己的引擎，天生合法）----
    def engine_move(self, state: chess.Board) -> Optional[chess.Move]:
        return self.ai.best_move(state)

    # ---- 终局 / 轮次 ----
    def is_terminal(self, state: chess.Board) -> dict:
        if not state.is_game_over():
            return {"over": False, "winner": None, "reason": ""}
        res = state.result()
        winner = {"1-0": "white", "0-1": "black", "1/2-1/2": "draw"}.get(res, "draw")
        if state.is_checkmate():
            reason = "checkmate"
        elif state.is_stalemate():
            reason = "stalemate"
        elif state.is_insufficient_material():
            reason = "insufficient_material"
        else:
            reason = "draw"
        return {"over": True, "winner": winner, "reason": reason, "result": res}

    def my_turn(self, state: chess.Board, my_side: str) -> bool:
        return self.side_to_move(state) == my_side

    def side_to_move(self, state: chess.Board) -> str:
        return "white" if state.turn == chess.WHITE else "black"

    # ---- 形势评分（给认输/求和）：白方视角的子力分（厘兵），正=白好、负=黑好。
    #      对弈树按 my_side 翻转成"我方视角"。是真实确定性计算（数子），不是 LLM 心算。
    _PIECE_CP = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330,
                 chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 0}

    def evaluate(self, state: chess.Board) -> int:
        score = 0
        for _, piece in state.piece_map().items():
            v = self._PIECE_CP[piece.piece_type]
            score += v if piece.color == chess.WHITE else -v
        return score

    def should_resign(self, state: chess.Board, my_side: str) -> bool:
        """这一拍局面是否已差到该认输（我方视角形势分 ≤ 阈值）。是否真认还要行为树确认连续够多拍——
        认输的"何时认"是棋种相关的，放适配器里（别的棋可重写：如五子棋永不认）。阈值在 config。"""
        my_eval = self.evaluate(state)
        if my_side == "black":
            my_eval = -my_eval
        return my_eval <= config.GAME_RESIGN_EVAL

    # ---- 翻成世界 move 命令 ----
    def to_command(self, state: chess.Board, move: chess.Move) -> dict:
        piece = state.piece_at(move.from_square)
        cmd = {
            "from": chess.square_name(move.from_square),
            "to": chess.square_name(move.to_square),
            "piece": _vision.LETTER[piece.piece_type] if piece else None,
        }
        if move.promotion:
            cmd["promotion"] = chess.piece_symbol(move.promotion)  # 'q'/'r'/'b'/'n'
        return cmd

    def move_uci(self, move: chess.Move) -> str:
        return move.uci()

    def describe(self, state: chess.Board, move: chess.Move) -> str:
        try:
            return state.san(move)        # 须在 push 之前算
        except Exception:
            return move.uci()


# 启动即注册（可插拔注册表）
register_adapter(ChessAdapter())
