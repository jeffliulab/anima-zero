"""sim-chess 世界本体 —— 一张能托管 chess / 五子棋 / 围棋 的「棋桌」。

它握**唯一真值**（python-chess Board / GomokuBoard / GoBoard）；负责判命令成败、推进棋局、判终局、渲染、跑内置电脑。

**v0.4 简化**：对大脑（ANIMA）**只暴露一个动作 `move`**，且 perceive 的 state 为空 `{}`——棋盘真值/轮次/胜负
一概不给，ANIMA 全靠**看画面**。旧的「选边就座 / 配对手 / 点开始 / phase 三阶段 / controllers」整套开局仪式
**已撤**：那是把简单事搞复杂了，也是通用大脑"绕过下棋技能、乱点仪式工具"的诱因。现在——
- **ANIMA 走子**：直接 `move`（查合法 → 落子）；轮到谁走由 python-chess 的走子合法性天然管（白手只能白走），
  ANIMA 靠自己的信念盘判断该不该出手，世界不替它把关。
- **对手（人 / 内置电脑）= 世界自己网页上的事**：网页配「内置电脑走哪方（bot_side ∈ 白/黑/无）」、人点子走、开新局。
  用一个内部小状态 `bot_side` 替掉旧的 controllers/phase。人点子 / 内置电脑走子都走同一条「查合法 → 落子」。

对局是否结束：chess 看 `board.is_game_over()`，加一个 `over` 布尔兜住"认输"这类非自然终局。没有"未开始"这种态——
盘一直在、从第 1 手就能走。
"""
from __future__ import annotations

import importlib.util
import json
import os
import threading
import time
from pathlib import Path

import chess

import go
import gomoku
import render

WORLD_VERSION = os.getenv("SIMCHESS_VERSION", "0.4")    # 世界版本(env 可覆盖,不 inline 写死)

SEATS = ("white", "black")
GAMES = ("chess", "gomoku", "go")


# ---- 加载世界自己的内置棋手引擎（跨仓，仅此处碰；与 ANIMA 的引擎相互独立）----
def _engine_path() -> str:
    env = os.getenv("SIMCHESS_ENGINE_PATH")
    if env:
        return env
    root = Path(__file__).resolve().parents[4]
    return str(root / "3-anima-chess-engine" / "chess" / "engine.py")


def _load_engine():
    spec = importlib.util.spec_from_file_location("simchess_engine", _engine_path())
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_engine_mod = _load_engine()


# ---- AWI 工具声明：对大脑只有 move 一个动作 ----
MOVE_TOOL = {
    "name": "move",
    "description": (
        "把 from 格（我识别为 piece 的）子走到 to 格。世界拿真值试这步："
        "识别错 / from 没子 / 不合法（含没轮到你走的一方）→ 失败；成了 → 成功。只回成败，不回局面——"
        "局面你自己看画面。轮到谁走由走子合法性天然管：白子只能在白方回合走。"
    ),
    "parameters": {"type": "object",
                   "properties": {
                       "from": {"type": "string", "description": "起格，如 e2"},
                       "to": {"type": "string", "description": "目标格，如 e4"},
                       "piece": {"type": "string", "description": "你识别的子 P/N/B/R/Q/K（可选，核对识别）"},
                       "promotion": {"type": "string", "description": "升变 q/r/b/n（可选）"}},
                   "required": ["from", "to"]},
    "kind": "tool",
}
_TOOLS = [MOVE_TOOL]


def _other(seat: str) -> str:
    return "black" if seat == "white" else "white"


class SimChessWorld:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.game = "chess"                              # 当前棋种 chess/gomoku/go（世界网页可切=换桌）
        self.board = chess.Board()                       # chess 真值
        self.gomoku: gomoku.GomokuBoard | None = None
        self.go: go.GoBoard | None = None
        # 内部小状态：内置电脑走哪方（"white"/"black"/None=没有内置电脑）。替掉旧的 controllers/phase。
        # env 可覆盖（仅测试方便）：SIMCHESS_BOT_SIDE=white/black。
        bs = (os.getenv("SIMCHESS_BOT_SIDE") or "").strip().lower()
        self.bot_side: str | None = bs if bs in SEATS else None
        self.over = False                                # 对局是否已结束（自然终局 or 认输）
        self.result: str = ""                            # "" | "white" | "black" | "draw"
        self.bot = _engine_mod.AI(depth=int(os.getenv("SIMCHESS_BOT_DEPTH", "3")),
                                  time_limit=float(os.getenv("SIMCHESS_BOT_TIME", "2.0")))
        self.last = ""
        self.selected_sq: str | None = None
        self._game_seq = 0                               # 对弈档案的递增编号
        self._logged_game = False                        # 当前这盘是否已落档（防重复）

    # ================= 内部：棋种无关的小工具 =================
    def _fresh_board(self) -> None:
        """按当前棋种重建一张干净的盘。"""
        if self.game == "gomoku":
            self.gomoku = gomoku.GomokuBoard()
        elif self.game == "go":
            self.go = go.GoBoard()
        else:
            self.board = chess.Board()
        self._logged_game = False                        # 新盘 = 新的一局，可再次落档

    def _stone_board(self):
        """五子棋/围棋的落子盘对象（chess 返回 None）。"""
        if self.game == "gomoku":
            return self.gomoku
        if self.game == "go":
            return self.go
        return None

    def _current_side(self) -> str:
        sb = self._stone_board()
        if sb is not None:
            return sb.side_to_move()
        return "white" if self.board.turn == chess.WHITE else "black"

    def _winner_now(self) -> tuple[bool, str]:
        """当前局面是否自然终局 + 赢家（white/black/draw）。围棋占位永不终局。"""
        if self.game == "chess":
            if not self.board.is_game_over():
                return False, ""
            res = self.board.result()
            return True, {"1-0": "white", "0-1": "black"}.get(res, "draw")
        if self.game == "gomoku" and self.gomoku is not None:
            if not self.gomoku.is_over():
                return False, ""
            return True, self.gomoku.winner() or "draw"
        return False, ""    # go 占位：无胜负

    def _check_terminal(self) -> None:
        """一手之后判自然终局：终局则 over=True、记 result、落档。持锁内调用。"""
        won, winner = self._winner_now()
        if won:
            self.over = True
            self.result = winner
            self._log_game_record()

    # 对弈档案落盘目录 = anima-zero/logs（env 可覆盖，不 inline 写死）。
    _GAMES_DIR = os.getenv("SIMCHESS_GAMES_LOG_DIR") or str(Path(__file__).resolve().parents[2] / "logs")

    def _log_game_record(self) -> None:
        """把【完整对局】落一行到 logs/games-*.jsonl —— 世界自己的对弈档案，供**独立 eval**事后复盘评分。
        **真数据**：chess 直接取 board.move_stack 的 UCI，绝不伪造；非 chess 暂只记结果。一盘只记一次。"""
        if self._logged_game or self.game != "chess" or not self.board.move_stack:
            return
        try:
            self._game_seq += 1
            rec = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "game_id": self._game_seq,
                "game": self.game,
                "bot_side": self.bot_side,                # 内置电脑走哪方（None=没有内置电脑）
                "result": self.result,                    # "white"/"black"/"draw"/""（弃局未分胜负）
                "plies": self.board.fullmove_number,
                "moves": [m.uci() for m in self.board.move_stack],   # 双方完整走子（UCI）
            }
            os.makedirs(self._GAMES_DIR, exist_ok=True)
            path = os.path.join(self._GAMES_DIR, "games-" + time.strftime("%Y-%m-%d") + ".jsonl")
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            self._logged_game = True
        except Exception:
            pass   # 落档失败绝不影响对局

    # ================= AWI 能力声明 =================
    def capabilities(self) -> dict:
        # 对大脑只有 move；state_schema 空 = perceive 不给任何结构化真值，全靠画面。
        return {"name": "sim-chess", "version": WORLD_VERSION, "tools": _TOOLS, "state_schema": {}}

    # ================= 看（perceive 的回程：只有画面，state 空） =================
    def render_image(self):
        """渲染当前棋种一帧（持锁拷贝、出锁渲染，防撕裂）。chess 带选子高亮。"""
        with self.lock:
            kind, sel = self.game, self.selected_sq
            if kind == "gomoku" and self.gomoku is not None:
                snap = self.gomoku.copy()
            elif kind == "go" and self.go is not None:
                snap = self.go.copy()
            else:
                snap = self.board.copy()
        if kind == "gomoku" and isinstance(snap, gomoku.GomokuBoard):
            return gomoku.render_gomoku(snap)
        if kind == "go" and isinstance(snap, go.GoBoard):
            return go.render_go(snap)
        return render.render_board(snap, sel)

    def observe(self) -> tuple[dict, bytes]:
        """只给画面；state 为空 {}（棋盘真值/轮次/胜负一概不给，大脑靠看）。"""
        return {}, render.to_png(self.render_image())

    # ================= 动（AWI invoke：大脑只有 move） =================
    def invoke(self, name: str, **args) -> dict:
        if name == "move":
            return self._move(args)
        return {"ok": False, "message": f"未知能力：{name}（本世界对大脑只有 move）"}

    def _apply_chess_move(self, frm: str, to: str, promotion: str | None, declared_piece: str | None):
        """持锁内：查合法 → 落子。返回 {ok, message}。ANIMA 走子 / 人点子走 共用这条。"""
        if self.over or self.game != "chess":
            return {"ok": False, "message": "当前不在进行的象棋对局中"}
        mv = self._build_move(frm, to, promotion)
        if mv is None:
            return {"ok": False, "message": f"坐标无法解析：{frm}->{to}"}
        sq_piece = self.board.piece_at(mv.from_square)
        if sq_piece is None:
            return {"ok": False, "message": f"{frm} 上没有子"}
        if declared_piece:
            actual = render.LETTER[sq_piece.piece_type]
            if declared_piece.strip().upper() != actual:
                return {"ok": False, "message": f"识别错：{frm} 是 {actual}，你说是 {declared_piece.strip().upper()}"}
        if mv not in self.board.legal_moves:      # 含"没轮到这一方"（白手在黑回合就不在 legal_moves）
            return {"ok": False, "message": f"不合法：{frm}->{to}"}
        self.board.push(mv)
        self.last = mv.uci()
        self._check_terminal()
        return {"ok": True, "message": f"已走 {mv.uci()}"}

    def _move(self, args: dict) -> dict:
        """ANIMA 的 move：查合法 → 落子。无 phase/controller 门槛——轮次靠走子合法性天然管。"""
        with self.lock:
            return self._apply_chess_move(args.get("from", ""), args.get("to", ""),
                                          args.get("promotion"), args.get("piece"))

    def _build_move(self, frm: str, to: str, promotion: str | None):
        try:
            a = chess.parse_square(frm.strip().lower())
            b = chess.parse_square(to.strip().lower())
        except Exception:
            return None
        promo = None
        if promotion:
            promo = {"q": chess.QUEEN, "r": chess.ROOK, "b": chess.BISHOP,
                     "n": chess.KNIGHT}.get(promotion.strip().lower())
        piece = self.board.piece_at(a)
        if promo is None and piece and piece.piece_type == chess.PAWN and chess.square_rank(b) in (0, 7):
            promo = chess.QUEEN
        return chess.Move(a, b, promotion=promo)

    # ================= 世界网页的事（人 / 内置电脑 / 换桌 / 复位；不对大脑暴露） =================
    def set_bot_side(self, side: str | None) -> dict:
        """网页配「内置电脑走哪方」：side ∈ white/black/None(无)。随时可改（不像旧的比赛中不许）。"""
        if side in ("", "none", "无", "None"):
            side = None
        if side is not None and side not in SEATS:
            return {"ok": False, "message": "内置电脑只能走 white / black / 无"}
        with self.lock:
            self.bot_side = side
            self.last = f"内置电脑走 {side or '无'}"
            return {"ok": True, "bot_side": self.bot_side}

    def human_click_move(self, frm: str, to: str, promotion: str | None = None) -> dict:
        """人在网页点子走（象棋）。轮到内置电脑的那一方，人不能替它走。"""
        with self.lock:
            self.selected_sq = None
            if self.game != "chess":
                return {"ok": False, "message": "当前不是象棋"}
            if self._current_side() == self.bot_side:
                return {"ok": False, "message": "现在轮到内置电脑走。"}
            return self._apply_chess_move(frm, to, promotion, None)

    def human_place(self, r: int, c: int) -> dict:
        """人在五子棋/围棋盘上落子。轮到内置电脑的那一方，人不能替它走。"""
        with self.lock:
            if self.over:
                return {"ok": False, "message": "对局已结束。"}
            sb = self._stone_board()
            if sb is None:
                return {"ok": False, "message": "当前不是落子类棋种"}
            if sb.side_to_move() == self.bot_side:
                return {"ok": False, "message": "现在轮到内置电脑走。"}
            ok, msg = sb.place(r, c)
            if ok:
                self.last = f"落子 ({r},{c})"
                self._check_terminal()
            return {"ok": ok, "message": msg}

    def select_square(self, sq: str | None) -> dict:
        """人点了起子格 → 记下来给渲染画高亮圈（不走子）。无效/空 → 清掉。"""
        with self.lock:
            if not sq:
                self.selected_sq = None
                return {"ok": True, "selected": None}
            try:
                chess.parse_square(sq.strip().lower())
            except Exception:
                self.selected_sq = None
                return {"ok": False, "message": f"不是合法格：{sq}"}
            self.selected_sq = sq.strip().lower()
            return {"ok": True, "selected": self.selected_sq}

    def switch_game(self, kind: str) -> dict:
        """换棋种=换桌：重置成该棋种新盘、开新局。"""
        with self.lock:
            if kind not in GAMES:
                return {"ok": False, "message": f"只支持 {'/'.join(GAMES)}"}
            self._log_game_record()                       # 换桌前：进行中的 chess 先存档
            self.game = kind
            self.selected_sq = None
            self.over = False
            self.result = ""
            self._fresh_board()
            self.last = f"切换棋种 → {kind}"
            return {"ok": True, "game": kind}

    def resign(self, side: str) -> dict:
        """网页：某一方认输 → 对局结束、判对方胜。"""
        with self.lock:
            if side not in SEATS:
                return {"ok": False, "message": "认输方只能是 white/black"}
            if self.over:
                return {"ok": False, "message": "对局已结束。"}
            self.over = True
            self.result = _other(side)
            self._log_game_record()
            self.last = f"{side} 认输"
            return {"ok": True, "result": self.result}

    def reset(self) -> dict:
        """开新局：当前棋种干净盘、清结束态（bot_side 保留，由网页单独配）。"""
        with self.lock:
            self._log_game_record()                       # 复位前：进行中的 chess 先存档
            self.selected_sq = None
            self.over = False
            self.result = ""
            self._fresh_board()
            self.last = "开新局"
            return {"ok": True}

    # ---------- 内置电脑：轮到 bot_side 那一方且未终局就自动走（server 后台每拍调） ----------
    def bot_step(self) -> bool:
        with self.lock:
            if self.bot_side is None or self.over:
                return False
            sb = self._stone_board()
            if sb is not None:
                if sb.side_to_move() != self.bot_side or sb.is_over():
                    return False
                ok, _ = sb.bot_move() if hasattr(sb, "bot_move") else (False, "")
                if ok and sb.moves:
                    r, c, _col = sb.moves[-1]
                    self.last = f"内置电脑落子 ({r},{c})"
                    self._check_terminal()
                return ok
            if self._current_side() != self.bot_side or self.board.is_game_over():
                return False
            mv = self.bot.best_move(self.board)
            if mv is None:
                return False
            self.board.push(mv)
            self.last = f"内置电脑 {mv.uci()}"
            self._check_terminal()
            return True

    # ---------- 人类页/调试用的完整真值（不进 perceive，走 /status） ----------
    def status(self) -> dict:
        d = {
            "game": self.game,
            "bot_side": self.bot_side,
            "over": self.over,
            "turn": self._current_side(),
            "result": self.result,
            "last": self.last,
        }
        if self.game == "chess":
            b = self.board
            d.update({"fullmove": b.fullmove_number, "is_over": b.is_game_over(),
                      "fen": b.fen()})                   # fen 仅人类页/调试，绝不进 perceive
        else:
            sb = self._stone_board()
            n = sb.move_count() if sb is not None else 0
            d.update({"fullmove": n // 2 + 1, "is_over": bool(sb and sb.is_over()),
                      "board_px": (gomoku.board_px() if self.game == "gomoku" else go.board_px())})
        return d
