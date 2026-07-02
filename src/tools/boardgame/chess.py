"""象棋工具适配器（ChessAdapter）—— ANIMA 下国际象棋的整套原子能力：
视觉(read_board) + 引擎(engine_move) + 规则(python-chess) + 形势评分(evaluate)。

**解耦**：只有这个文件 import 你的引擎（`3-anima-chess-engine/chess/engine.py`，跨仓非包，用 importlib
按路径加载）。升级 ANIMA 棋力 = 只换它背后的引擎，行为树/skill/别的棋一行不动。**不改引擎源码，只在外面包。**

state = 一个 python-chess Board（ANIMA 期望的局面）；世界才是唯一真值，每拍用视觉校准。
"""
from __future__ import annotations

import importlib.util
import os
from typing import Optional

import chess

from ... import config
from . import _vision
from .base import OCC, PIECE, register_adapter


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

    def __init__(self, depth: int | None = None, time_limit: float | None = None,
                 recognizer=None) -> None:
        # 识别器注入（v0.5 视觉桥脚手架）：recognizer 有 `space`（OCC/PIECE）+ `read_detailed(png)`；
        # 不注入 → 老 `_vision` 模板匹配（PIECE 空间，sim-chess 2D 合成图专用）——行为逐字节不变。
        # 按世界选哪个识别器组合，在 skills launcher 接线（wave 5），这里只认抽象接口。
        self.recognizer = recognizer
        # 引擎双路：配了 ANIMA_ENGINE_URL → 经 MCP 调独立引擎 server（棋理顾问，MCP 多 server 用法）；
        # 没配 → 进程内加载引擎（默认；单测 / 无额外进程时用）。棋力升级只换背后的引擎，行为树/skill 不动。
        self._engine_url = (os.getenv("ANIMA_ENGINE_URL") or "").strip() or None
        if self._engine_url:
            self._engine = self.ai = None
        else:
            self._engine = _load_engine()
            depth = depth if depth is not None else config.CHESS_DEPTH
            time_limit = time_limit if time_limit is not None else config.CHESS_TIME
            self.ai = self._engine.AI(depth=depth, time_limit=time_limit)

    def new_state(self) -> chess.Board:
        return chess.Board()

    # ---- 视觉（经注入的识别器；不注入 = 老 _vision，行为不变）----
    @property
    def space(self) -> str:
        """当前识别器的观测空间（OCC/PIECE）。老 _vision 认子型 → PIECE。"""
        return getattr(self.recognizer, "space", PIECE)

    def read_board(self, image_png: bytes) -> dict:
        return self.read_board_detailed(image_png)[0]

    def read_board_detailed(self, image_png: bytes) -> tuple[dict, set]:
        if self.recognizer is not None:
            return self.recognizer.read_detailed(image_png)
        return _vision.read_board_detailed(image_png)

    def read_board_occupancy(self, image_png: bytes) -> tuple[dict, set]:
        """带置信度的占用读取（OCC 空间）。识别器原生在 OCC 就直接给；在 PIECE 就把子型盘塌成占用盘。"""
        placement, uncertain = self.read_board_detailed(image_png)
        if self.space == OCC:
            return placement, uncertain
        return self._collapse_occ(placement), uncertain

    def placement_of(self, state: chess.Board) -> dict:
        return _vision.placement_of_board(state)

    # ---- 观测空间投影 ----
    @staticmethod
    def _collapse_occ(piece_board: dict) -> dict:
        """子型盘 {sq:'P'/'n'} → 占用盘 {sq:'w'|'b'}（大写=白）。"""
        return {sq: ("w" if sym.isupper() else "b") for sq, sym in piece_board.items()}

    def _piece_of(self, state: chess.Board) -> dict:
        return _vision.placement_of_board(state)

    def _occ_of(self, state: chess.Board) -> dict:
        return self._collapse_occ(self._piece_of(state))

    def observed_of(self, state: chess.Board) -> dict:
        """state 在【当前识别器观测空间】的投影。PIECE 空间下与 placement_of 逐字节等价（老行为不变）。"""
        return self._occ_of(state) if self.space == OCC else self._piece_of(state)

    # ---- 轮次判断：观测摆放和 state 比，认出对手走的那一手 ----
    def diff_move(self, state: chess.Board, observed: dict) -> Optional[chess.Move]:
        # 观测与期望的比较一律在【同一观测空间】里做（observed_of）。OCC 空间信息比子型少：
        # 非吃子/非升变移动仍唯一可辨（from/to 占用变化唯一）；升变类同格多解 → 走下面的歧义返 None。
        if observed == self.observed_of(state):
            return None                                   # 没变 → 对手还没走
        matches = []                                      # 找出所有能产生 observed 的合法着法
        for mv in state.legal_moves:
            state.push(mv)
            same = self.observed_of(state) == observed
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
        if self._engine_url:
            return self._engine_move_mcp(state)
        return self.ai.best_move(state)

    def _engine_move_mcp(self, state: chess.Board) -> Optional[chess.Move]:
        """经 MCP 向独立引擎 server 求最优着（给 FEN → 回 UCI）。连不上 / 出错 → None（上层下拍重试）。
        这一路 MCP 流量也记进 awi_log（world="chess-engine"），在 /awi 流量区能看到大脑↔引擎的调用。"""
        import time as _t

        from ... import awi_log, config as _cfg
        from ...mcp_bridge import run_sync, with_session
        url = self._engine_url.rstrip("/") + "/mcp"

        async def op(s):
            r = await s.call_tool("best_move", {"fen": state.fen()})
            return "".join(c.text for c in r.content if getattr(c, "text", None))
        t0 = _t.perf_counter()
        try:
            uci = run_sync(with_session(url, op, _cfg.ENGINE_MCP_TIMEOUT),
                           _cfg.ENGINE_MCP_TIMEOUT + _cfg.BRIDGE_GRACE_S)
        except Exception as e:
            awi_log.record("chess-engine", "best_move", f"best_move → 失败({type(e).__name__})",
                           (_t.perf_counter() - t0) * 1000)
            return None
        awi_log.record("chess-engine", "best_move", f"best_move → {uci or '无子可走'}",
                       (_t.perf_counter() - t0) * 1000, resp={"uci": uci})
        return chess.Move.from_uci(uci) if uci else None

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

    # ---- 把一手逻辑棋拆成物理原语序列（按世界支持的原语） ----
    def expand_move(self, state: chess.Board, move: chess.Move, prims: set) -> list[dict]:
        b = state
        frm = chess.square_name(move.from_square)
        to = chess.square_name(move.to_square)
        piece = b.piece_at(move.from_square)
        letter = _vision.LETTER[piece.piece_type] if piece else None
        promo = chess.piece_symbol(move.promotion) if move.promotion else None

        # 数据世界（无 remove）：一步 move，吃子/易位/过路兵/升变全靠世界数据层一步吞。
        if "remove" not in prims:
            cmd = {"op": "move", "from": frm, "to": to, "piece": letter}
            if promo:
                cmd["promotion"] = promo
            return [cmd]

        # 物理世界（有 remove）：真拆成一连串原子物理动作。
        ops: list[dict] = []
        # 王车易位 = 王移 + 车移（不是吃子，单独处理）
        if b.is_castling(move):
            ops.append({"op": "move", "from": frm, "to": to, "piece": letter})
            rank = chess.square_rank(move.from_square)
            rf, rt = ((7, 5) if b.is_kingside_castling(move) else (0, 3))
            ops.append({"op": "move",
                        "from": chess.square_name(chess.square(rf, rank)),
                        "to": chess.square_name(chess.square(rt, rank)), "piece": "R"})
            return ops
        # 先把被吃的子移走：过路兵的被吃兵不在 to 格（在 to 同列、from 同行），普通吃子在 to 格。
        if b.is_en_passant(move):
            cap = chess.square(chess.square_file(move.to_square), chess.square_rank(move.from_square))
            ops.append({"op": "remove", "square": chess.square_name(cap)})
        elif b.is_capture(move):
            ops.append({"op": "remove", "square": to})
        # 走这一步
        ops.append({"op": "move", "from": frm, "to": to, "piece": letter})
        # 升变：把落到底线的兵换成新子（移走兵 + 摆上新子）；世界若没有 place 就退化成给 move 带 promotion 标记。
        if promo:
            if "place" in prims:
                ops.append({"op": "remove", "square": to})
                ops.append({"op": "place", "square": to, "piece": promo.upper()})
            else:
                ops[-1]["promotion"] = promo
        return ops

    # ---- 从一帧画面构造信念局面（半路接手 / 开局 seed）----
    def seed_from_vision(self, image_png: bytes, side_to_move: str = "white") -> chess.Board:
        return self.seed_from_placement(self.read_board(image_png), side_to_move)

    def verify_move_piece_level(self, state: chess.Board, move: chess.Move, piece_obs: dict) -> bool:
        """子型级交叉核对（裁判严格模式）：CNN 子型盘 piece_obs 与「走完 move 后应有的摆放」
        在 CNN 自信的格上是否吻合。只比双方都有话说的格（CNN 看不清的格不冤枉它）。"""
        b = state.copy(stack=False)
        b.push(move)
        expected = _vision.placement_of_board(b)
        for sq, sym in piece_obs.items():
            if sq in expected and expected[sq] != sym:
                return False
        for sq, sym in expected.items():
            if sq in piece_obs and piece_obs[sq] != sym:
                return False
        return True

    def seed_from_placement(self, placement: dict, side_to_move: str = "white") -> chess.Board:
        """从一张「子型摆放表」构造信念局面（seed_from_vision 的无图版；CNN 读数直接喂这里）。"""
        b = chess.Board(None)                            # 空盘
        for sq, sym in placement.items():
            try:
                b.set_piece_at(sq, chess.Piece.from_symbol(sym))
            except (ValueError, KeyError):
                continue                                 # 认到非法符号（如空格模板 / 占用色）→ 跳过
        b.turn = chess.WHITE if side_to_move == "white" else chess.BLACK
        try:
            b.set_castling_fen("KQkq")                   # python-chess 只保留与实际 K/R 位置一致的易位权
        except Exception:  # noqa: BLE001
            b.set_castling_fen("-")
        return b

    def move_uci(self, move: chess.Move) -> str:
        return move.uci()

    def describe(self, state: chess.Board, move: chess.Move) -> str:
        try:
            return state.san(move)        # 须在 push 之前算
        except Exception:
            return move.uci()


# 启动即注册（可插拔注册表）
register_adapter(ChessAdapter())
