"""sim-chess 世界本体 —— 一张能托管 chess / 五子棋 / 围棋 的「棋桌」，带正式状态机。

它握**唯一真值**（python-chess Board / GomokuBoard / GoBoard）；负责判命令成败、推进棋局、判终局、渲染、跑内置 bot。
world = 真实世界、它说了算：游戏流程（开始/暂停/恢复/认输/终局）的规则都在这里（物理规则，可硬编码）。

对大脑（ANIMA）**只给画面 + 命令成败 + 极简 state = `{controllers, phase}`**：
- controllers：谁坐哪一方（human/anima/bot/空），ANIMA 据此知道"自己执哪方、有没有被换下"。
- phase：游戏阶段（not_start/in_game/game_over）——三阶段。哪一阶段从静态画面看不出来（尤其"结束"vs"未开始"），必须显式声明。
**绝不给棋盘真值**（局面/FEN/轮次/胜负/棋种）——那些 ANIMA 必须自己从画面看。

席位控制者 ∈ {human, anima, bot, 空(None)}：human 人在网页点子走；anima 经 AWI invoke 走；bot 世界内置引擎走。
ANIMA 想下棋必须自己经 `take_seat` 工具选边就座（世界不替它默认/预设）。
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

WORLD_VERSION = os.getenv("SIMCHESS_VERSION", "0.2")    # 世界版本(env 可覆盖,不 inline 写死)

SEATS = ("white", "black")
GAMES = ("chess", "gomoku", "go")
CONTROLLERS = ("human", "anima", "bot")                 # 空席位 = None
# 阶段：未开始 / 比赛中 / 对弈结束（三阶段——不设全局暂停，要中断就复位/开新局）
NOT_START, IN_GAME, GAME_OVER = "not_start", "in_game", "game_over"


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


# ---- AWI 工具声明（描述是教 ANIMA「整套流程怎么走」的唯一渠道——靠描述，不靠脑里写死）----
TAKE_SEAT_TOOL = {
    "name": "take_seat",
    "description": (
        "开始对弈前，你**必须先选你执哪一方**（坐到一个空席位上）。seat 填 white 或 black。"
        "世界会判：该席位空着、且 anima 还没占别的席位，才让你坐；坐下后返回 {ok, seat, controllers}，"
        "你就知道自己执哪方了。坐下后，你可以用 seat_opponent 给对手那一席配人/电脑（也可由人在世界页配）；"
        "两方都有人后才能 start_game。"
    ),
    "parameters": {"type": "object",
                   "properties": {"seat": {"type": "string", "enum": list(SEATS),
                                           "description": "你要执的一方：white 或 black"}},
                   "required": ["seat"]},
    "kind": "tool",
}
# 对手可选控制者 = 除 anima（那是你自己）外的控制者；空席（None）不算"配对手"，故排除。
OPPONENT_OPTIONS = [c for c in CONTROLLERS if c != "anima"]   # ["human", "bot"]
SEAT_OPPONENT_TOOL = {
    "name": "seat_opponent",
    "description": (
        "你已 take_seat 选好自己那方后，用它**给对手那一席配上人或电脑**：who 填 human（真人陪你下）"
        "或 bot（世界内置引擎陪你下）。世界会把【你没坐的那一席】配成 who（你不用指定是哪一席）。"
        "得先 take_seat 才能用（否则世界不知道哪席是对手）；比赛中不能改。配好对手后就可以 start_game 开下。"
    ),
    "parameters": {"type": "object",
                   "properties": {"who": {"type": "string", "enum": list(OPPONENT_OPTIONS),
                                          "description": "对手是谁：human（真人）或 bot（电脑）"}},
                   "required": ["who"]},
    "kind": "tool",
}
START_GAME_TOOL = {
    "name": "start_game",
    "description": (
        "双方都就座后，开始这盘对弈。世界会判：两个席位都已配人（你已 take_seat、对手也已配上"
        "——你用 seat_opponent 配，或人在世界页配）才开始；缺人则失败并告诉你缺谁。"
        "开始后进入「比赛中」，你才能走子。"
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
    "kind": "tool",
}
MOVE_TOOL = {
    "name": "move",
    "description": (
        "把 from 格（我识别为 piece 的）子走到 to 格（**对弈进行中、轮到你时**才有效）。"
        "世界拿真值试这步：识别错 / from 没子 / 不合法 / 没轮到你 / 没在比赛中 → 失败；成了 → 成功。只回成败，不回局面。"
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
RESIGN_TOOL = {
    "name": "resign",
    "description": "认输：结束这盘、判你那一方负。「比赛中」可认输。",
    "parameters": {"type": "object", "properties": {}, "required": []},
    "kind": "tool",
}
_TOOLS = [TAKE_SEAT_TOOL, SEAT_OPPONENT_TOOL, START_GAME_TOOL, MOVE_TOOL, RESIGN_TOOL]


def _other(seat: str) -> str:
    return "black" if seat == "white" else "white"


class SimChessWorld:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.game = "chess"                              # 当前棋种 chess/gomoku/go（世界网页可切=换桌）
        self.board = chess.Board()                       # chess 真值
        self.gomoku: gomoku.GomokuBoard | None = None
        self.go: go.GoBoard | None = None
        # 席位默认【空】（None）——世界不替 ANIMA 预设/默认；env 可覆盖（仅测试方便）
        self.controllers: dict[str, str | None] = {
            "white": os.getenv("SIMCHESS_WHITE") or None,
            "black": os.getenv("SIMCHESS_BLACK") or None,
        }
        self.phase = NOT_START
        self.result: str = ""                            # "" | "white" | "black" | "draw"
        self.bot = _engine_mod.AI(depth=int(os.getenv("SIMCHESS_BOT_DEPTH", "3")),
                                  time_limit=float(os.getenv("SIMCHESS_BOT_TIME", "2.0")))
        self.last = ""
        self.selected_sq: str | None = None
        self._game_seq = 0                               # 对弈档案的递增编号
        self._logged_game = False                        # 当前这盘是否已落档（防重复：终局后再 reset 不重记）

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

    def _clear_seats(self) -> None:
        """清空两个席位（复位 / 换桌时调用）。复位后"没有任何 controller"，下一局重新配人——
        否则旧局的 human/anima/bot 会残留，挡住新局就座（曾经的真 bug：复位后 bot 还占着座）。"""
        self.controllers = {"white": None, "black": None}

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
        """当前局面是否终局 + 赢家（white/black/draw）。围棋占位永不终局。"""
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
        """一手之后判终局：终局则 phase→game_over、记 result。持锁内调用。"""
        over, winner = self._winner_now()
        if over:
            self.phase = GAME_OVER
            self.result = winner
            self._log_game_record()

    # 对弈档案落盘目录 = anima-zero/logs（与 awi/anima 日志同处；env 可覆盖，不 inline 写死）。
    _GAMES_DIR = os.getenv("SIMCHESS_GAMES_LOG_DIR") or str(Path(__file__).resolve().parents[2] / "logs")

    def _log_game_record(self) -> None:
        """把【完整对局】落一行到 logs/games-*.jsonl —— 世界自己的对弈档案，供**独立 eval**事后复盘评分。
        终局/认输/中途弃局时调用（持锁内）。**真数据**：chess 直接取 board.move_stack 的 UCI，绝不伪造；
        非 chess 暂只记结果（完整 move 细节 eval 用不到）。一盘只记一次（_logged_game 去重）。"""
        if self._logged_game or self.game != "chess" or not self.board.move_stack:
            return
        try:
            self._game_seq += 1
            rec = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "game_id": self._game_seq,
                "game": self.game,
                "white": self.controllers.get("white"),
                "black": self.controllers.get("black"),
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

    def _seats_filled(self) -> bool:
        return self.controllers["white"] is not None and self.controllers["black"] is not None

    def _seat_conflict(self, seat: str, controller: str | None) -> str | None:
        """约束：人可两次、anima/bot 各一次。冲突返回原因串，否则 None。"""
        if controller in (None, "human"):
            return None
        if self.controllers.get(_other(seat)) == controller:
            return f"{controller} 只能占一方（已在 {_other(seat)}）"
        return None

    def _anima_seat(self) -> str | None:
        for s in SEATS:
            if self.controllers.get(s) == "anima":
                return s
        return None

    # ================= AWI 能力声明 =================
    def capabilities(self) -> dict:
        # 角色就座靠 take_seat 工具（其 seat 枚举即可选角色）；不再单独声明 seats（已删的死机制）。
        # state_schema：声明 perceive.state 的键与含义，给 /awi 面板读（不靠缓存猜）；真值（局面/FEN）走 /status、不进此。
        return {"name": "sim-chess", "version": WORLD_VERSION, "tools": _TOOLS,
                "state_schema": {
                    "controllers": "谁坐哪一方：{white, black} → human | anima | bot | null(空席)",
                    "phase": "对局阶段：not_start | in_game | game_over",
                }}

    # ================= 看（perceive 的回程：画面 + 极简 state） =================
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
        """给画面 + 极简 state = {controllers, phase}。绝不给局面/FEN/轮次/胜负/棋种。"""
        png = render.to_png(self.render_image())
        with self.lock:
            state = {"controllers": dict(self.controllers), "phase": self.phase}
        return state, png

    # ================= 动（AWI invoke：ANIMA 的全部动作都经这里） =================
    def invoke(self, name: str, **args) -> dict:
        """ANIMA 的动作分派。requester 一律视为 'anima'（AWI 通道就是大脑）。每个动词先查 phase 合法性。"""
        if name == "move":
            return self._move(args, by="anima")
        if name == "take_seat":
            return self.take_seat(args.get("seat", ""))
        if name == "seat_opponent":
            return self.seat_opponent(args.get("who", ""))
        if name == "start_game":
            return self.start_game()
        if name == "resign":
            return self.resign(by="anima")
        return {"ok": False, "message": f"未知能力：{name}"}

    # ---------- 配置（未开始/对弈结束 时允许；比赛中不能改，要先复位/开新局） ----------
    def take_seat(self, seat: str) -> dict:
        """ANIMA 选边就座：坐到一个空席位（这就是「选执方」）。世界当裁判。"""
        with self.lock:
            if seat not in SEATS:
                return {"ok": False, "message": f"没有「{seat}」这个席位（只有 white/black）"}
            # 幂等：已经坐在这一席 → 直接成功（即便已开赛也不报错）。脑/人重复就座是常事，
            # 不该因"对弈进行中"把一个其实已经满足的就座请求判失败（消除"已坐却被阶段挡"的卡壳）。
            if self.controllers.get(seat) == "anima":
                return {"ok": True, "seat": seat, "controllers": dict(self.controllers), "noop": True}
            if self.phase not in (NOT_START, GAME_OVER):
                return {"ok": False, "message": "对弈进行中不能就座；要换边请先复位 / 开新局。"}
            cur = self.controllers.get(seat)
            if cur is not None:                          # 非 None 且非 anima（上面已 return）= 被别人占
                return {"ok": False, "message": f"{seat} 已被 {cur} 占，请选另一方或让人在世界页腾出席位。"}
            conflict = self._seat_conflict(seat, "anima")
            if conflict:
                return {"ok": False, "message": conflict}
            self.controllers[seat] = "anima"
            self.last = f"anima 就座 {seat}"
            return {"ok": True, "seat": seat, "controllers": dict(self.controllers)}

    def seat_opponent(self, who: str) -> dict:
        """ANIMA 给【对手那一席】配人/电脑：找到 anima 自己坐的席 → 把另一席配成 who。
        必须先 take_seat（否则不知道哪席是对手）；who 只能是 human/bot（不能配 anima/空）。
        校验/落座全交给 set_controller（比赛中不许、席位冲突等），这里只负责"算出对手是哪一席"。"""
        if who not in OPPONENT_OPTIONS:
            return {"ok": False, "message": f"对手只能是 {'/'.join(OPPONENT_OPTIONS)}（human=真人、bot=电脑）"}
        with self.lock:                                   # 只在锁内读"我坐哪席"，随即释放——set_controller 自带锁
            mine = self._anima_seat()
        if mine is None:
            return {"ok": False, "message": "你还没就座——请先 take_seat 选你执哪方，我才知道哪一席是对手。"}
        return self.set_controller(_other(mine), who)

    def set_controller(self, seat: str, controller: str | None) -> dict:
        """配/换某一席控制者（人/anima/bot/空）。比赛中不许（要先复位/开新局）。不动棋盘局面。"""
        if controller in ("", "空", "none", "None"):
            controller = None
        with self.lock:
            if seat not in SEATS:
                return {"ok": False, "message": f"没有「{seat}」这个席位"}
            if controller is not None and controller not in CONTROLLERS:
                return {"ok": False, "message": "控制者只能是 人/anima/bot/空"}
            if self.phase == IN_GAME:
                return {"ok": False, "message": "比赛中不能换人，请先复位 / 开新局。"}
            conflict = self._seat_conflict(seat, controller)
            if conflict:
                return {"ok": False, "message": conflict}
            self.controllers[seat] = controller
            self.last = f"配座 {seat}={controller or '空'}"
            return {"ok": True, "seat": seat, "controllers": dict(self.controllers)}

    def switch_game(self, kind: str) -> dict:
        """换棋种=换桌：重置成该棋种新盘、清空座位、回未开始。比赛中不许（先复位/开新局）。"""
        with self.lock:
            if kind not in GAMES:
                return {"ok": False, "message": f"只支持 {'/'.join(GAMES)}"}
            if self.phase == IN_GAME:
                return {"ok": False, "message": "比赛中不能换棋种，请先复位 / 开新局。"}
            self._log_game_record()                       # 换桌前：若有进行了一半的 chess 棋局，先存档（弃局也可供 eval 复盘）
            self.game = kind
            self.selected_sq = None
            self.phase = NOT_START
            self.result = ""
            self._clear_seats()                           # 换桌=彻底重来：座位也清空，重新配人
            self._fresh_board()
            self.last = f"切换棋种 → {kind}"
            return {"ok": True, "game": kind, "phase": self.phase}

    # ---------- 生命周期：开始/认输/复位（开新局） ----------
    def start_game(self) -> dict:
        """开始（含从 game_over 开新局）：双方就座 → 干净盘 + 进入比赛中。"""
        with self.lock:
            if self.phase not in (NOT_START, GAME_OVER):
                return {"ok": False, "message": "现在不能开始（要在未开始/对弈结束时）。"}
            if not self._seats_filled():
                empty = [s for s in SEATS if self.controllers[s] is None]
                return {"ok": False, "message": f"还有席位没配人：{'、'.join(empty)}。请配齐双方再开始。"}
            self._fresh_board()
            self.phase = IN_GAME
            self.result = ""
            self.selected_sq = None
            self.last = "开始对弈"
            return {"ok": True, "phase": self.phase, "controllers": dict(self.controllers)}

    def resign(self, by: str, side: str | None = None) -> dict:
        """认输：side 给了就那方认；没给则按 by 推（anima=anima 那席）。→ game_over。"""
        with self.lock:
            if self.phase != IN_GAME:
                return {"ok": False, "message": "现在没有进行中的对局可认输。"}
            seat = side if side in SEATS else (self._anima_seat() if by == "anima" else None)
            if seat is None:
                return {"ok": False, "message": "认不出是哪一方认输。"}
            self.phase = GAME_OVER
            self.result = _other(seat)
            self._log_game_record()
            self.last = f"{seat} 认输"
            return {"ok": True, "phase": self.phase, "result": self.result}

    def reset(self) -> dict:
        """复位/开新局：当前棋种干净盘、清空座位、回未开始。复位后没有任何 controller——
        下一局重新配人就座（这正是"复原后应当没有 controller"的预期，也腾出被 bot/人占住的席位）。"""
        with self.lock:
            self._log_game_record()                       # 复位前：若有进行了一半的 chess 棋局，先存档
            self.selected_sq = None
            self.phase = NOT_START
            self.result = ""
            self._clear_seats()                           # 复位=干净重来：座位也清空（修旧 bug：以前只清盘不清座）
            self._fresh_board()
            self.last = "复位"
            return {"ok": True, "phase": self.phase, "controllers": dict(self.controllers)}

    # ---------- 走子（三种来源；都只在比赛中、轮到该方） ----------
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

    def _move(self, args: dict, by: str) -> dict:
        """ANIMA 的 move（象棋）。持锁内原子校验：比赛中 ∧ 轮到 by 控的方 ∧ 合法。"""
        with self.lock:
            if self.phase != IN_GAME:
                return {"ok": False, "message": "现在不在比赛中（先 start_game / 等恢复）。"}
            if self.game != "chess":
                return {"ok": False, "message": "落子失败：当前棋盘无法识别这步"}
            side = self._current_side()
            if self.controllers.get(side) != by:
                return {"ok": False, "message": f"现在不是 {by}（{side} 由 {self.controllers.get(side)} 控制）"}
            frm, to = args.get("from", ""), args.get("to", "")
            mv = self._build_move(frm, to, args.get("promotion"))
            if mv is None:
                return {"ok": False, "message": f"坐标无法解析：{frm}->{to}"}
            sq_piece = self.board.piece_at(mv.from_square)
            if sq_piece is None:
                return {"ok": False, "message": f"{frm} 上没有子"}
            declared_piece = (args.get("piece") or "").strip().upper()   # ANIMA 声称识别到的子（可选，核对视觉）
            if declared_piece:
                actual = render.LETTER[sq_piece.piece_type]
                if declared_piece != actual:
                    return {"ok": False, "message": f"识别错：{frm} 是 {actual}，你说是 {declared_piece}"}
            if mv not in self.board.legal_moves:
                return {"ok": False, "message": f"不合法：{frm}->{to}"}
            self.board.push(mv)
            self.last = f"{by} {mv.uci()}"
            self._check_terminal()
            return {"ok": True, "message": f"已走 {mv.uci()}"}

    # ---------- 人类页：点子走 / 落子 ----------
    def human_click_move(self, frm: str, to: str, promotion: str | None = None) -> dict:
        with self.lock:
            if self.phase != IN_GAME:
                return {"ok": False, "message": "现在不在比赛中。"}
            if self.game != "chess":
                return {"ok": False, "message": "当前不是象棋"}
            self.selected_sq = None
            side = self._current_side()
            if self.controllers.get(side) != "human":
                return {"ok": False, "message": f"现在不是人走（{side} 由 {self.controllers.get(side)} 控制）"}
            mv = self._build_move(frm, to, promotion)
            if mv is None or mv not in self.board.legal_moves:
                return {"ok": False, "message": f"不合法：{frm}->{to}"}
            self.board.push(mv)
            self.last = f"human {mv.uci()}"
            self._check_terminal()
            return {"ok": True, "message": f"已走 {mv.uci()}"}

    def human_place(self, r: int, c: int) -> dict:
        """人在五子棋/围棋盘上落子。"""
        with self.lock:
            if self.phase != IN_GAME:
                return {"ok": False, "message": "现在不在比赛中。"}
            sb = self._stone_board()
            if sb is None:
                return {"ok": False, "message": "当前不是落子类棋种"}
            side = sb.side_to_move()
            if self.controllers.get(side) != "human":
                return {"ok": False, "message": f"现在不是人走（{side} 由 {self.controllers.get(side)} 控制）"}
            ok, msg = sb.place(r, c)
            if ok:
                self.last = f"human 落子 ({r},{c})"
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

    # ---------- 内置 bot：只在比赛中、轮到 bot 才走 ----------
    def bot_step(self) -> bool:
        with self.lock:
            if self.phase != IN_GAME:
                return False
            sb = self._stone_board()
            if sb is not None:
                side = sb.side_to_move()
                if self.controllers.get(side) != "bot" or sb.is_over():
                    return False
                ok, _ = sb.bot_move() if hasattr(sb, "bot_move") else (False, "")
                if ok and sb.moves:
                    r, c, _col = sb.moves[-1]
                    self.last = f"bot 落子 ({r},{c})"
                    self._check_terminal()
                return ok
            side = self._current_side()
            if self.controllers.get(side) != "bot" or self.board.is_game_over():
                return False
            mv = self.bot.best_move(self.board)
            if mv is None:
                return False
            self.board.push(mv)
            self.last = f"bot {mv.uci()}"
            self._check_terminal()
            return True

    # ---------- 人类页/调试用的完整真值（不进 perceive 双流） ----------
    def status(self) -> dict:
        d = {
            "game": self.game,
            "phase": self.phase,
            "controllers": dict(self.controllers),
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
