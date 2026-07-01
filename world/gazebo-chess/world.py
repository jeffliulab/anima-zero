"""gazebo-chess 世界本体：sim-chess 那张棋桌的 Gazebo 物理版。

对大脑（ANIMA）只给画面（俯视相机帧）+ 极简 state `{controllers, phase}`，绝不给棋盘真值——和 sim-chess 一样。
区别只有一个：`move` 不再瞬间改数据，而是**让真实机械臂跑一趟抓放**（arm_controller），放完核对。

v0.4 最小版：默认 `free_move`（盘上一个子，move(from,to)=把 from 格的子真夹起来搬到 to 格），
不要求合法对局——这就是「能把一个子从 X 挪到 Y、跑通 infra」。完整对局/吃子/失败补救是 0.5。

线程：所有 ROS 操作（臂动作、刷相机帧）在 self.lock 内同步做（ArmController 用 spin_until_future_complete，
单线程）。FastAPI handler 并发时靠这把锁串行化访问 ROS 节点。move 会占锁数秒，期间 perceive 等一下——
v0.4 冒烟可接受。
"""
from __future__ import annotations

import os
import threading
import time

import rclpy

import config
import geometry
import render
import spawn
from arm_controller import ArmController

SEATS = ("white", "black")
CONTROLLERS = ("human", "anima", "bot")
NOT_START, IN_GAME, GAME_OVER = "not_start", "in_game", "game_over"

FREE_MOVE = os.getenv("GZCHESS_FREE_MOVE", "1") == "1"   # v0.4 默认：一个子自由挪，不查棋规

# ---- AWI 工具声明（和 sim-chess 同名同义，大脑侧四件套因此零改动可用）----
TAKE_SEAT_TOOL = {
    "name": "take_seat",
    "description": "选边就座：坐到一个空席位（white/black）。坐下才轮得到你走子。",
    "parameters": {"type": "object", "properties": {"seat": {"type": "string", "description": "white 或 black"}},
                   "required": ["seat"]},
    "kind": "tool",
}
START_GAME_TOOL = {
    "name": "start_game",
    "description": "双方就座后开始这局。开始后才能 move。",
    "parameters": {"type": "object", "properties": {}, "required": []},
    "kind": "tool",
}
MOVE_TOOL = {
    "name": "move",
    "description": ("把 from 格的子搬到 to 格——机械臂真夹真放。放完世界核对是否到位，只回成败、不回局面。"
                    "（v0.4：盘上一个子时直接搬它。）"),
    "parameters": {"type": "object",
                   "properties": {"from": {"type": "string", "description": "起格，如 e2"},
                                  "to": {"type": "string", "description": "目标格，如 e4"}},
                   "required": ["from", "to"]},
    "kind": "tool",
}
RESIGN_TOOL = {"name": "resign", "description": "认输，结束这局。", "parameters": {"type": "object", "properties": {}, "required": []}, "kind": "tool"}
_TOOLS = [TAKE_SEAT_TOOL, START_GAME_TOOL, MOVE_TOOL, RESIGN_TOOL]

# perceive 的 state 契约声明（键名 + 一句含义）——由世界【模块声明】，给 /awi 面板读；
# 这样面板不靠「缓存上一次 perceive」猜，离线也知道这世界 state 长什么样。绝不含棋盘真值（真值走 /status）。
STATE_SCHEMA = {
    "controllers": "谁坐哪一方：{white, black} → human | anima | bot | null(空席)",
    "phase": "对局阶段：not_start | in_game | game_over",
}

# 停臂驻位（让出俯视相机视野；和 _tune_camera 一致）
PARK = [float(x) for x in os.getenv("GZCHESS_PARK_JOINTS", "2.5,0,0,0,0,0").split(",")]


class GazeboChessWorld:
    def __init__(self, demo_piece_square: str | None = None) -> None:
        self.lock = threading.RLock()
        self.controllers: dict[str, str | None] = {"white": None, "black": None}
        self.phase = NOT_START
        self.last = ""
        # ROS：一个节点（ArmController）+ 挂相机订阅
        if not rclpy.ok():
            rclpy.init()
        self.arm = ArmController()
        self.cam = render.CameraFeed(self.arm)
        self.ready = self.arm.wait_ready(20)
        # 布场景：棋盘 + 相机 +（演示子）；停臂驻位
        self._setup(demo_piece_square or os.getenv("GZCHESS_DEMO_PIECE", "e2"))

    def _spin(self, n: int = 5) -> None:
        for _ in range(n):
            rclpy.spin_once(self.arm, timeout_sec=0.05)

    def _setup(self, demo_square: str) -> None:
        with self.lock:
            spawn.spawn_board()
            spawn.spawn_camera()
            if demo_square:
                spawn.spawn_piece(demo_square, "white")
            if self.ready:
                self.arm.goto_arm(PARK, 3.0)
            time.sleep(1.0)
            self._spin(20)

    # ---------- AWI ----------
    def capabilities(self) -> dict:
        return {"name": "gazebo-chess", "version": config.WORLD_VERSION, "tools": _TOOLS,
                "state_schema": STATE_SCHEMA}

    def debug_state(self) -> dict:
        """【人类调试台专用·世界真值，绝不给 ANIMA】走世界本地 /status。
        返回 perceive 故意藏起来的东西：不光谁坐哪方/阶段，还有**每个棋子现在真实在哪格 + 精确位姿**。
        这就是人的『上帝视角』，和 perceive（只给 controllers/phase）明确分开。"""
        with self.lock:
            self._spin(4)
            pieces = {}
            for nm, pp in spawn.all_model_poses(window_s=0.8).items():   # 短窗口:调试台要快点响应
                if not nm.startswith("piece_"):
                    continue
                pieces[nm] = {"square": geometry.base_xy_to_square(pp[0], pp[1]),
                              "xyz": [round(v, 4) for v in pp]}
            return {"controllers": dict(self.controllers), "phase": self.phase, "pieces": pieces}

    def observe(self) -> tuple[dict, bytes | None]:
        """给画面（俯视相机帧 PNG）+ 极简 state。绝不给棋盘真值。"""
        with self.lock:
            self._spin(6)
            png = render.to_png(self.cam.frame)
            state = {"controllers": dict(self.controllers), "phase": self.phase}
        return state, png

    def stream_jpeg(self) -> bytes | None:
        with self.lock:
            self._spin(3)
            return render.to_jpeg(self.cam.frame)

    def invoke(self, name: str, **args) -> dict:
        if name == "move":
            return self._move(args)
        if name == "take_seat":
            return self._take_seat(args.get("seat", ""))
        if name == "start_game":
            return self._start_game()
        if name == "resign":
            return self._resign()
        if name == "seat_opponent":
            return self._seat_opponent(args.get("who", ""))
        return {"ok": False, "message": f"未知能力：{name}"}

    # ---------- 席位 / 阶段（mirror sim-chess 的极简版）----------
    def _take_seat(self, seat: str) -> dict:
        with self.lock:
            if seat not in SEATS:
                return {"ok": False, "message": "席位只有 white/black"}
            if self.controllers.get(seat) == "anima":
                return {"ok": True, "seat": seat, "controllers": dict(self.controllers), "noop": True}
            if self.phase not in (NOT_START, GAME_OVER):
                return {"ok": False, "message": "对弈中不能就座，先复位/开新局"}
            if self.controllers.get(seat) is not None:
                return {"ok": False, "message": f"{seat} 已被占"}
            self.controllers[seat] = "anima"
            return {"ok": True, "seat": seat, "controllers": dict(self.controllers)}

    def _seat_opponent(self, who: str) -> dict:
        with self.lock:
            if who not in ("human", "bot"):
                return {"ok": False, "message": "对手只能 human/bot"}
            mine = next((s for s in SEATS if self.controllers.get(s) == "anima"), None)
            if mine is None:
                return {"ok": False, "message": "先 take_seat"}
            other = "black" if mine == "white" else "white"
            self.controllers[other] = who
            return {"ok": True, "seat": other, "controllers": dict(self.controllers)}

    def _start_game(self) -> dict:
        with self.lock:
            if self.phase == IN_GAME:
                return {"ok": True, "message": "已在对弈中", "noop": True}
            # v0.4：盘上有子、有人就座即可开
            if not any(v == "anima" for v in self.controllers.values()):
                return {"ok": False, "message": "你还没就座（take_seat）"}
            self.phase = IN_GAME
            return {"ok": True, "message": "开始"}

    def _resign(self) -> dict:
        with self.lock:
            self.phase = GAME_OVER
            return {"ok": True, "message": "认输，结束"}

    def _piece_at(self, square: str):
        """按当前位置找某格上的子：返回 (model_name, (x,y,z))，没有则 (None, None)。
        判据：piece_* 模型里，(x,y) 离该格中心最近且在半格内。"""
        import math
        ex, ey, _ = geometry.square_surface_xyz(square)
        best, bestd = None, 1e9
        for nm, pp in spawn.all_model_poses().items():
            if not nm.startswith("piece_"):
                continue
            d = math.hypot(pp[0] - ex, pp[1] - ey)
            if d < bestd:
                best, bestd, bestp = nm, d, pp
        if best is not None and bestd <= config.CELL_M * 0.6:
            return best, bestp
        return None, None

    # ---------- move = 真实抓放 ----------
    def _move(self, args: dict) -> dict:
        frm, to = (args.get("from", "") or "").strip().lower(), (args.get("to", "") or "").strip().lower()
        with self.lock:
            if self.phase != IN_GAME:
                return {"ok": False, "message": "现在不在对弈中（先 start_game）"}
            if not self.ready:
                return {"ok": False, "message": "机械臂/MoveIt 没就绪"}
            try:
                geometry.parse_square(frm); geometry.parse_square(to)
            except ValueError as e:
                return {"ok": False, "message": f"格名非法：{e}"}
            if not FREE_MOVE:
                return {"ok": False, "message": "v0.4 只支持 free_move（一个子）；完整对局是 0.5"}
            # 按**当前位置**找 from 格上的子（不靠名字——子走了一步后名字还是 spawn 时的，位置才准）
            name, p = self._piece_at(frm)
            if name is None:
                return {"ok": False, "message": f"{frm} 格上没有子"}
            gx, gy, gz = p[0], p[1], p[2] + config.PIECE_GRASP_WAIST_M
            ok, msg = self.arm.pick_at(gx, gy, gz)
            if not ok:
                return {"ok": False, "message": f"抓取失败：{msg}"}
            dx, dy, dz = geometry.grasp_xyz(to)
            ok, msg = self.arm.place_at(dx, dy, dz)
            if not ok:
                return {"ok": False, "message": f"放置失败：{msg}"}
            # 自检：子是否到了 to 格
            time.sleep(1.0)
            self._spin(10)
            p2 = spawn.model_pose(name)
            exp = geometry.square_surface_xyz(to)
            import math
            err = math.hypot(p2[0] - exp[0], p2[1] - exp[1]) if p2 else 9.99
            self.arm.goto_arm(PARK, 3.0)   # 走完回驻位，让出相机视野
            self._spin(10)
            if err <= config.PLACE_TOLERANCE_M:
                self.last = f"anima {frm}->{to}"
                return {"ok": True, "message": f"已把子从 {frm} 搬到 {to}（落点误差 {err*100:.1f}cm）"}
            return {"ok": False, "message": f"放偏了：落点离 {to} 中心 {err*100:.1f}cm"}

    def shutdown(self) -> None:
        try:
            self.arm.destroy_node()
        except Exception:  # noqa: BLE001
            pass
