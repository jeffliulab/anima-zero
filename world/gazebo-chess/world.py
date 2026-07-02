"""gazebo-chess 世界本体：一个「纯物理」的机械臂棋盘世界（新框架）。

对大脑（ANIMA）只给**画面**（俯视相机帧）+ **三个物理原语**——不含棋规、不含开局仪式、不判合法：
- `move(from,to)` ：把 from 格的子**裸搬**到 to 格（真夹真放，不判棋规——大脑才是裁判）。
- `remove(square)`：把 square 格的子夹起来、放到棋盘一侧的**弃子区**（吃子/清子）。
- `place(square,piece)`：从**备用子区**取一枚该色的新子、摆到 square（摆盘/升变）。

大脑靠 adapter.expand_move 把一手逻辑棋拆成这几个原语的序列（吃子=remove+move、升变=move+remove+place…）。
世界只负责把每个原语真做出来 + 回成败，绝不碰"轮到谁/是否终局/合法性"（那些在大脑）。

state（perceive 随画面给大脑的结构化部分）= **空 `{}`**：这个世界没有该给大脑的结构化真值，棋盘全靠画面看。
棋盘真值（每子在哪格）只走人类调试台 /status（debug_state），绝不给 ANIMA。

线程（v0.5 wave 0）：ROS 的 spin 收敛到**唯一一个专职线程**（SingleThreadedExecutor，init 时启动）——
相机帧、/joint_states、service/action 回包全由它持续送达；请求工作线程对 ROS future 只「挂事件+带超时等」
（见 arm_controller._wait_future），**绝不自己 spin**（从请求线程 spin 会和 DDS/executor 撞线程，实测卡死）。
世界状态的互斥仍靠 self.lock（move 期间 observe 等锁属已知残余，登记在案）。
长动作进度（v0.5 wave 0）：`invoke` 声明了 keyword-only `_progress`——awi_mcp 签名探测到它，就把
MCP progress 上报函数传进来；三个原语分阶段报人话进度（定位→抓取→搬运→放置→核对），大脑靠这些
"生命迹象"续命等待，用户在仪表盘/对弈面板实时看到臂在干什么。不带 _progress 调用（如测试）行为不变。
"""
from __future__ import annotations

import math
import os
import threading
import time

import rclpy

import config
import geometry
import render
import spawn
from arm_controller import ArmController

# ---- AWI 工具声明：三个物理原语（大脑侧靠这仨的 expand_move 拆一手棋）----
MOVE_TOOL = {
    "name": "move",
    "description": "把 from 格的子搬到 to 格——机械臂真夹真放（裸搬，不判棋规）。放完核对落点，只回成败。",
    "parameters": {"type": "object",
                   "properties": {"from": {"type": "string", "description": "起格，如 e2"},
                                  "to": {"type": "string", "description": "目标格，如 e4"}},
                   "required": ["from", "to"]},
    "kind": "tool",
}
REMOVE_TOOL = {
    "name": "remove",
    "description": "把某格的子从盘上夹起、放到棋盘一侧的弃子区（吃子/清子时用）。只回成败。",
    "parameters": {"type": "object",
                   "properties": {"square": {"type": "string", "description": "要清掉的格，如 e5"}},
                   "required": ["square"]},
    "kind": "tool",
}
PLACE_TOOL = {
    "name": "place",
    "description": "从备用子区取一枚棋子、摆到某格（摆盘/升变时用）。piece 用棋子字母：大写=白、小写=黑（如 Q/q）。只回成败。",
    "parameters": {"type": "object",
                   "properties": {"square": {"type": "string", "description": "要摆到的格，如 e1"},
                                  "piece": {"type": "string", "description": "棋子字母，大写白/小写黑，如 Q/q/P/p"}},
                   "required": ["square", "piece"]},
    "kind": "tool",
}
_TOOLS = [MOVE_TOOL, REMOVE_TOOL, PLACE_TOOL]

# perceive 的 state 契约声明（给 /awi 面板读）——这个世界没有该给大脑的结构化 state，故为空。
STATE_SCHEMA: dict = {}

# 停臂驻位（让出俯视相机视野；和 _tune_camera 一致）
PARK = [float(x) for x in os.getenv("GZCHESS_PARK_JOINTS", "2.5,0,0,0,0,0").split(",")]

# 进度上报的粗颗粒阶段占比（0~1）：只是给人看的进度语义（定位→抓→搬→放→核对），不是精确测量。
_P_LOCATE, _P_PICK, _P_CARRY, _P_PLACE, _P_VERIFY = 0.1, 0.25, 0.5, 0.7, 0.9


class GazeboChessWorld:
    def __init__(self, demo_piece_square: str | None = None) -> None:
        self.lock = threading.RLock()
        self.last = ""
        self._discard_n = 0                 # 已用掉几个弃子槽（remove 递增）
        # ROS：一个节点（ArmController）+ 挂相机订阅
        if not rclpy.ok():
            rclpy.init()
        self.arm = ArmController()
        self.cam = render.CameraFeed(self.arm)
        # 专职 ROS spin 线程：唯一允许 spin 这个节点的地方（回调异常只记日志，不许杀线程）。
        self._executor = rclpy.executors.SingleThreadedExecutor()
        self._executor.add_node(self.arm)
        self._spin_alive = True
        threading.Thread(target=self._spin_forever, name="gzchess-ros-spin", daemon=True).start()
        self.ready = self.arm.wait_ready(config.READY_TIMEOUT_S)
        # 布场景：棋盘 + 相机 +（演示子）；停臂驻位
        self._setup(demo_piece_square or os.getenv("GZCHESS_DEMO_PIECE", "e2"))

    def _spin_forever(self) -> None:
        while self._spin_alive and rclpy.ok():
            try:
                self._executor.spin_once(timeout_sec=config.SPIN_STEP_S)
            except Exception:  # noqa: BLE001  回调抛错不许杀掉唯一的 spin 线程
                pass

    def _spin(self, n: int = 5) -> None:
        """等专职 spin 线程送达新数据的节拍（历史名保留：以前是自己 spin，现在只等）。"""
        time.sleep(n * config.SPIN_STEP_S)

    def _setup(self, demo_square: str) -> None:
        with self.lock:
            spawn.spawn_board()
            spawn.spawn_camera()
            fen = config.SETUP_FEN.strip()
            if fen:                                     # v0.5 多子：按 FEN 摆放字段摆盘
                self._spawn_fen(fen)
            elif demo_square:                           # v0.4 单演示子路径原样保留（追加不替换）
                spawn.spawn_piece(demo_square, "white")
            if self.ready:
                self.arm.goto_arm(PARK, config.MOVE_TIME_APPROACH_S)
            time.sleep(config.SETTLE_S)
            self._spin(20)

    @staticmethod
    def _spawn_fen(fen: str) -> None:
        """按 FEN 的【摆放字段】摆多子（大写白/小写黑；不管轮次/易位权——那是大脑的事）。
        手工解析、不引 python-chess（世界 venv 不为此加依赖；FEN 摆放字段语法是域常量级的简单格式）。"""
        rows = fen.split()[0].split("/")
        for i, row in enumerate(rows[:8]):
            rank = 7 - i                                 # FEN 第一行是 rank8
            file = 0
            for ch in row:
                if ch.isdigit():
                    file += int(ch)
                    continue
                if ch.lower() in "pnbrqk" and file < 8:
                    sq = geometry.square_name(file, rank)
                    spawn.spawn_piece(sq, "white" if ch.isupper() else "black", kind=ch.lower())
                    file += 1

    # ---------- AWI ----------
    def capabilities(self) -> dict:
        return {"name": "gazebo-chess", "version": config.WORLD_VERSION, "tools": _TOOLS,
                "state_schema": STATE_SCHEMA}

    def debug_state(self) -> dict:
        """【人类调试台专用·世界真值，绝不给 ANIMA】走世界本地 /status。
        返回每个棋子现在真实在哪格 + 精确位姿——这是人的『上帝视角』，和 perceive（给空 state）明确分开。"""
        with self.lock:
            self._spin(4)
            pieces = {}
            for nm, pp in spawn.all_model_poses(window_s=config.STATUS_POSE_WINDOW_S).items():   # 短窗口:调试台要快点响应
                if not nm.startswith("piece_"):
                    continue
                pieces[nm] = {"square": geometry.base_xy_to_square(pp[0], pp[1]),
                              "xyz": [round(v, 4) for v in pp]}
            return {"pieces": pieces, "discard_used": self._discard_n}

    def observe(self) -> tuple[dict, bytes | None]:
        """给画面（俯视相机帧 PNG）+ 空 state。绝不给棋盘真值。"""
        with self.lock:
            self._spin(6)
            png = render.to_png(self.cam.frame)
        return {}, png

    def stream_jpeg(self) -> bytes | None:
        with self.lock:
            self._spin(3)
            return render.to_jpeg(self.cam.frame)

    def invoke(self, name: str, *, _progress=None, **args) -> dict:
        # `_progress(比例, 人话消息)` 由 awi_mcp 签名探测注入（MCP progress 上报）；没有就静默。
        note = _progress or (lambda p, m="": None)
        if name == "move":
            return self._move(args, note)
        if name == "remove":
            return self._remove((args.get("square", "") or "").strip().lower(), note)
        if name == "place":
            return self._place((args.get("square", "") or "").strip().lower(), args.get("piece", ""), note)
        return {"ok": False, "message": f"未知能力：{name}"}

    # ---------- 按当前位置找某格上的子 ----------
    def _piece_at(self, square: str):
        """返回 (model_name, (x,y,z))，没有则 (None, None)。判据：piece_* 模型里 (x,y) 离该格中心最近且在半格内。"""
        ex, ey, _ = geometry.square_surface_xyz(square)
        best, bestp, bestd = None, None, 1e9
        for nm, pp in spawn.all_model_poses().items():
            if not nm.startswith("piece_"):
                continue
            d = math.hypot(pp[0] - ex, pp[1] - ey)
            if d < bestd:
                best, bestd, bestp = nm, d, pp
        if best is not None and bestd <= config.CELL_M * config.PIECE_MATCH_CELL_FRAC:
            return best, bestp
        return None, None

    def _park(self) -> None:
        if self.ready:
            self.arm.goto_arm(PARK, config.MOVE_TIME_APPROACH_S)
            self._spin(10)

    # ---------- move = 裸搬（真夹真放，不判棋规）----------
    def _move(self, args: dict, note=lambda p, m="": None) -> dict:
        frm = (args.get("from", "") or "").strip().lower()
        to = (args.get("to", "") or "").strip().lower()
        with self.lock:
            if not self.ready:
                return {"ok": False, "message": "机械臂/MoveIt 没就绪"}
            try:
                geometry.parse_square(frm); geometry.parse_square(to)
            except ValueError as e:
                return {"ok": False, "message": f"格名非法：{e}"}
            name, p = self._piece_at(frm)          # 按当前位置找（子走一步后名字不变、位置才准）
            if name is None:
                return {"ok": False, "message": f"{frm} 格上没有子"}
            note(_P_LOCATE, f"已定位 {frm} 上的棋子，正在规划抓取")
            gx, gy, gz = p[0], p[1], p[2] + config.PIECE_GRASP_WAIST_M
            ok, msg = self.arm.pick_at(gx, gy, gz, progress=lambda m: note(_P_PICK, m))
            if not ok:
                self._park(); return {"ok": False, "message": f"抓取失败：{msg}"}
            note(_P_CARRY, f"已夹取，正在移向 {to}")
            dx, dy, dz = geometry.grasp_xyz(to)
            ok, msg = self.arm.place_at(dx, dy, dz, progress=lambda m: note(_P_PLACE, m))
            if not ok:
                self._park(); return {"ok": False, "message": f"放置失败：{msg}"}
            note(_P_VERIFY, "已放下，正在核对落点")
            time.sleep(config.SETTLE_S); self._spin(10)
            p2 = spawn.model_pose(name)
            exp = geometry.square_surface_xyz(to)
            err = math.hypot(p2[0] - exp[0], p2[1] - exp[1]) if p2 else 9.99
            self._park()
            if err <= config.PLACE_TOLERANCE_M:
                self.last = f"move {frm}->{to}"
                return {"ok": True, "message": f"已把子从 {frm} 搬到 {to}（落点误差 {err * 100:.1f}cm）"}
            return {"ok": False, "message": f"放偏了：落点离 {to} 中心 {err * 100:.1f}cm"}

    # ---------- remove = 夹起丢弃子区 ----------
    def _remove(self, square: str, note=lambda p, m="": None) -> dict:
        with self.lock:
            if not self.ready:
                return {"ok": False, "message": "机械臂/MoveIt 没就绪"}
            try:
                geometry.parse_square(square)
            except ValueError as e:
                return {"ok": False, "message": f"格名非法：{e}"}
            name, p = self._piece_at(square)
            if name is None:
                return {"ok": False, "message": f"{square} 格上没有子"}
            note(_P_LOCATE, f"已定位 {square} 上的棋子，准备夹去弃子区")
            gx, gy, gz = p[0], p[1], p[2] + config.PIECE_GRASP_WAIST_M
            ok, msg = self.arm.pick_at(gx, gy, gz, progress=lambda m: note(_P_PICK, m))
            if not ok:
                self._park(); return {"ok": False, "message": f"抓 {square} 的子失败：{msg}"}
            note(_P_CARRY, "已夹取，正在移向弃子区")
            dx, dy, dz = geometry.discard_grasp_xyz(self._discard_n)
            ok, msg = self.arm.place_at(dx, dy, dz, progress=lambda m: note(_P_PLACE, m))
            self._park()
            if not ok:
                return {"ok": False, "message": f"丢到弃子区失败：{msg}"}
            self._discard_n += 1
            self.last = f"remove {square}"
            return {"ok": True, "message": f"已把 {square} 的子移到弃子区（第 {self._discard_n} 个）"}

    # ---------- place = 从备用子区取子摆上盘 ----------
    def _place(self, square: str, piece: str, note=lambda p, m="": None) -> dict:
        with self.lock:
            if not self.ready:
                return {"ok": False, "message": "机械臂/MoveIt 没就绪"}
            try:
                geometry.parse_square(square)
            except ValueError as e:
                return {"ok": False, "message": f"格名非法：{e}"}
            letter = (piece or "").strip()
            if not letter or letter.lower() not in "pnbrqk":
                return {"ok": False, "message": f"piece 非法：{piece!r}（应为棋子字母 P/N/B/R/Q/K，大写白小写黑）"}
            color = "white" if letter.isupper() else "black"
            note(_P_LOCATE, f"在备用子区备一枚{color}子")
            rx, ry, rz = geometry.reservoir_spawn_xyz()
            ok, nm = spawn.spawn_piece_at((rx, ry, rz), color, kind=letter.lower())
            if not ok:
                return {"ok": False, "message": f"备用子区取子失败：{nm}"}
            time.sleep(config.SPAWN_SETTLE_S); self._spin(8)
            grx, gry, grz = geometry.reservoir_grasp_xyz()
            ok, msg = self.arm.pick_at(grx, gry, grz, progress=lambda m: note(_P_PICK, m))
            if not ok:
                self._park(); return {"ok": False, "message": f"从备用区抓子失败：{msg}"}
            note(_P_CARRY, f"已从备用区夹取，正在移向 {square}")
            dx, dy, dz = geometry.grasp_xyz(square)
            ok, msg = self.arm.place_at(dx, dy, dz, progress=lambda m: note(_P_PLACE, m))
            self._park()
            if not ok:
                return {"ok": False, "message": f"摆到 {square} 失败：{msg}"}
            self.last = f"place {letter}@{square}"
            return {"ok": True, "message": f"已把一枚{color}子摆到 {square}"}

    def shutdown(self) -> None:
        self._spin_alive = False
        try:
            self._executor.shutdown(timeout_sec=1.0)
        except Exception:  # noqa: BLE001
            pass
        try:
            self.arm.destroy_node()
        except Exception:  # noqa: BLE001
            pass
