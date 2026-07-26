"""sim-house-nav 世界对象 —— 实现 AWI 三件事：capabilities() / observe() / invoke()。

这个世界 = 一套住宅（Domus 资产库里的场景）+ 一台会用真实步态走路的机器人，头上一只前视相机。
ANIMA 只能【看画面】+【发导航原语】，靠自己认出身处哪间屋、决定往哪走。

⛔ 给大脑的观测里**绝不含**坐标、房间名、屋子地图——那是世界的上帝视角真值（走 /status，
   只给人看、用于验收）。房间必须靠看画面认出来，这正是本 demo 要考的能力。
   给的是真实机器人身上本来就有的东西：相机画面 + IMU 朝向 + 自身是否摔倒。
⛔ 说明书（GUIDANCE）里也不许写「屋子里有哪些房间、摆着什么」——理由见 GUIDANCE 上方那段。
"""
from __future__ import annotations

import math

import config as C
import domus_scene
from domus_scene import layout
from guidance import GUIDANCE  # noqa: F401  （世界说明书，server.py 从这里 import）
from sim import HouseSim

L = layout()          # Domus 场景的布局定义（只给 /status 判房间用，绝不进 AWI 观测）

class HouseNavWorld:
    """AWI 世界对象。动作真的驱动物理，观测真的来自相机。"""

    def __init__(self) -> None:
        self.sim = HouseSim()
        self.sim.start()
        self._last_event = "（还没动过）"
        self._sweep: list[tuple[str, bytes]] | None = None   # look_around 拍的那一组，等下次感知取走

    # ---------------------------------------------------------------- 能力声明
    def capabilities(self) -> dict:
        """告诉大脑这个世界有哪些原子动作。参数用 JSON schema 描述，带默认值与范围说明。

        ┌─ 动作清单（改这里务必同步更新这张表、README 与 GUIDANCE）────────────────────┐
        │ 名字            作用                    参数            会不会移动位置        │
        │ move_forward    朝正前方走一段          meters 0~MAX    会（前进）            │
        │ turn_left       原地逆时针转            degrees 0~MAX   不会（只改朝向）      │
        │ turn_right      原地顺时针转            degrees 0~MAX   不会（只改朝向）      │
        │ look_around     原地转一圈拍一组照片    views 3~8       不会（大致转回原朝向）│
        └────────────────────────────────────────────────────────────────────────────┘
        四个动作**并列**，没有主次：前三个是移动原语（把高层意图翻成速度指令交给步态策略），
        look_around 是观察原语（把"转一圈看看"这件本来要来回四趟的事并成一次）。
        ⛔ 四个都不含任何导航智能——往哪走、这是哪间屋、找到没有，全由大脑看画面判断。
        """
        return {
            "name": "sim-house-nav",
            "tools": [
                {
                    "name": "move_forward",
                    "description": (
                        f"让机器人朝当前正前方走一段距离（米）。最多一次 {C.MAX_MOVE_M:g} 米。"
                        "它用真实步态行走，实际距离会有出入；前面太近会自动刹车站住、"
                        "撞上墙或家具会走不动，两种情况我都如实告诉你走了多远、前面还剩多远。"
                        "⛔ 我不会替你绕开障碍——想走多远、走不动了怎么办，都由你决定。"),
                    "kind": "tool",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "meters": {
                                "type": "number",
                                "description": f"想往前走多远（米），0 到 {C.MAX_MOVE_M:g}",
                                "default": C.DEFAULT_MOVE_M,
                            },
                        },
                        "required": ["meters"],
                    },
                },
                {
                    "name": "turn_left",
                    "description": (
                        f"机器人原地向左（逆时针）转一个角度。最多一次 {C.MAX_TURN_DEG:g} 度。"
                        "转完站定，方便你重新看画面。"),
                    "kind": "tool",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "degrees": {
                                "type": "number",
                                "description": f"向左转多少度，0 到 {C.MAX_TURN_DEG:g}",
                                "default": C.DEFAULT_TURN_DEG,
                            },
                        },
                        "required": ["degrees"],
                    },
                },
                {
                    "name": "turn_right",
                    "description": (
                        f"机器人原地向右（顺时针）转一个角度。最多一次 {C.MAX_TURN_DEG:g} 度。"
                        "转完站定，方便你重新看画面。"),
                    "kind": "tool",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "degrees": {
                                "type": "number",
                                "description": f"向右转多少度，0 到 {C.MAX_TURN_DEG:g}",
                                "default": C.DEFAULT_TURN_DEG,
                            },
                        },
                        "required": ["degrees"],
                    },
                },
                *([{
                    "name": "look_around",
                    "description": (
                        "原地转一圈环视四周：我会带着它**逆时针转满 360 度**，沿途等距拍几张照片，"
                        f"下一次感知一次性把这一组画面全给你（默认 {C.SWEEP_VIEWS} 张，每张标着"
                        "它是相对你原来朝向左转多少度拍的）。位置不变；转完**大致**回到原来的朝向"
                        "（真实步态转一圈会差几度，我会把实际转了多少如实告诉你）。\n"
                        "什么时候用它：进了一个新地方、想知道四周都有什么、或者被挡住要找出路时。"
                        "比你自己「转一次→看一眼」来回好几趟省事得多。"),
                    "kind": "tool",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "views": {
                                "type": "integer",
                                "description": (f"转一圈拍几张，{C.SWEEP_VIEWS_MIN} 到 {C.SWEEP_VIEWS_MAX}；"
                                                "张数越多越细但越慢"),
                                "default": C.SWEEP_VIEWS,
                            },
                        },
                    },
                }] if C.LOOK_AROUND else []),
            ],
        }

    # ---------------------------------------------------------------- 感知
    def observe(self):
        """(state, image_png) —— 大脑每轮看到的东西。

        state 里只放机器人**自身**能感知到的：朝向（IMU）、是否摔倒、上一个动作的结果。
        ⛔ 不放 x/y 坐标、不放房间名——那是上帝视角。
        """
        _x, _y, yaw = self.sim.pose()
        state = {
            "heading_deg": round(math.degrees(yaw) % 360.0, 1),   # IMU 罗盘朝向（真机也有）
            # 激光测距：八个方向各能直着走多远(m)。和罗盘一样是机器人自己身上的传感器读数。
            # ⛔ 不是地图：它只说"朝这个方位走能走多远"，不说那儿是什么、更不说房间名。
            "clearance_m": self.sim.clearances(),
            # 正前方那个锥（不是一条线）里最近的东西 —— 刹车就是照它判的。
            # 为什么要单给：一条中心线会从门缝里穿过去报"前面 8 米空着"，而肩膀其实要撞上。
            # 两个数差很大 = 中间那条线通着、两侧有东西（实测出生点旁就有这么一处）。
            "front_cone_m": round(self.sim.front_clearance(), 2),
            "fallen": self.sim.fallen(),
            "last_action": self._last_event,
        }
        # 刚做过 look_around：把那一圈照片整组交出去（走多相机通道，大脑本来就支持一轮多图）。
        # 取一次即清——它是"上一个动作的产物"，不是持续状态；下一轮回到正常的单帧当前画面。
        if self._sweep is not None:
            shots, self._sweep = self._sweep, None
            state["cameras"] = [name for name, _png in shots]     # 顺序=图的顺序（AWI 约定）
            return state, shots
        return state, self.sim.frame_png()

    # ---------------------------------------------------------------- 世界配置（AWI 声明通道）
    CONFIG_KEY = "body"     # 这个世界只有一项可配：装的是哪台机器人

    def config(self) -> dict:
        """我有哪些可配置项、每项能选什么、现在是哪个。

        ⚠️ 这是**声明**，不是操作入口——改它走带外的 `POST /config`（和 `/reset` 一个类别），
        因为换身体是**人**在开跑前做的场地配置，不是大脑在对话中途该做的事
        （换身体要重建整个仿真，位置姿态全没了）。大脑读到的只是"你现在是什么身体"，
        就像真机器人知道自己是什么身体一样。
        选项**从 Domus 的机器人清单现读**，不在这儿另抄一份名单。
        """
        rs = domus_scene.robots()
        return {
            "options": [{
                "key": self.CONFIG_KEY,
                "label": "身体",
                "description": "这个世界里站着哪台机器人。切换会重建仿真，机器人回到出生点。",
                "value": self.sim.robot_key,
                "choices": [{"value": k, "label": v["label"]} for k, v in rs.ROBOTS.items()],
            }],
        }

    def set_config(self, key: str, value: str) -> dict:
        """换身体：把整个仿真重建一遍。带外调用（网页），不走 AWI。"""
        if key != self.CONFIG_KEY:
            return {"ok": False, "message": f"这个世界没有「{key}」这项配置。"}
        rs = domus_scene.robots()
        if value not in rs.ROBOTS:
            return {"ok": False,
                    "message": f"没有名叫「{value}」的机器人。现有：{', '.join(rs.ROBOTS)}"}
        if value == self.sim.robot_key:
            return {"ok": True, "message": f"本来就是{rs.ROBOTS[value]['label']}，没改动。",
                    "config": self.config()}
        old = self.sim
        try:
            new = HouseSim(robot_key=value)     # 换模型、换策略，构造失败就保持原样
        except Exception as e:
            return {"ok": False, "message": f"换成「{value}」失败，仍在用原来那台：{e}"}
        old.stop()                              # 新的建成了才停旧的，免得中途两头空
        self.sim = new
        self.sim.start()
        self._last_event = "（刚换了身体，放在出生点）"
        self._sweep = None
        return {"ok": True,
                "message": f"已换成{rs.ROBOTS[value]['label']}，放回出生点。",
                "config": self.config()}

    # ---------------------------------------------------------------- 动作
    def invoke(self, name: str, *, _progress=None, **args) -> dict:
        if name == "move_forward":
            return self._move_forward(float(args.get("meters", C.DEFAULT_MOVE_M)), _progress)
        if name == "turn_left":
            return self._turn(float(args.get("degrees", C.DEFAULT_TURN_DEG)), +1, _progress)
        if name == "turn_right":
            return self._turn(float(args.get("degrees", C.DEFAULT_TURN_DEG)), -1, _progress)
        if name == "look_around":
            if not C.LOOK_AROUND:      # 关着就当没有这个动作，绝不"关了还能调"
                return {"ok": False, "message": "这个世界现在没有「环视」这个动作。"}
            return self._look_around(int(args.get("views", C.SWEEP_VIEWS)), _progress)
        return {"ok": False, "message": f"这个世界没有「{name}」这个动作。"}

    def _look_around(self, views: int, _progress=None) -> dict:
        n = max(C.SWEEP_VIEWS_MIN, min(views, C.SWEEP_VIEWS_MAX))
        note = "" if n == views else f"（你要求 {views} 张，我按 {C.SWEEP_VIEWS_MIN}~{C.SWEEP_VIEWS_MAX} 张的范围取了 {n}）"
        if _progress:
            _progress(C.PROGRESS_START, f"开始环视，转一圈拍 {n} 张…")
        shots, r = self.sim.sweep(n)
        if not shots:
            self._last_event = "环视时没拍到画面"
            return {"ok": False, "message": "环视失败：一张画面都没取到。", "data": r}
        self._sweep = shots                       # 交给下一次感知（走多相机通道）
        if r["fallen"]:
            self._last_event = f"环视转到一半摔倒了（拍到 {len(shots)} 张）"
            return {"ok": False,
                    "message": f"环视转到一半摔倒了，只拍到 {len(shots)} 张{note}。",
                    "data": r}
        self._last_event = f"环视了一圈，拍了 {len(shots)} 张"
        return {"ok": True,
                "message": (f"环视完毕，转了一圈拍了 {len(shots)} 张{note}——这一组画面在下一次"
                            f"感知时一起给你，每张标着是相对原朝向左转多少度拍的。位置没变。"),
                "data": r}

    def _move_forward(self, meters: float, _progress=None) -> dict:
        if meters <= 0:
            return {"ok": False, "message": "要走的距离得是正数。"}
        capped = min(meters, C.MAX_MOVE_M)
        note = "" if capped == meters else f"（你要求 {meters:g} 米，一次最多 {C.MAX_MOVE_M:g} 米，我按上限走）"
        if _progress:
            _progress(C.PROGRESS_START, f"开始往前走 {capped:g} 米…")
        r = self.sim.drive_distance(capped)     # 闭环：走到实测位移达标为止
        moved = r["moved_m"]
        if r["fallen"]:
            self._last_event = "刚才往前走的时候摔倒了"
            return {"ok": False, "message": f"糟糕，走的过程中摔倒了（只挪了 {moved:.2f} 米）。", "data": r}
        # 撞前刹车：还没碰上就主动停住了（真机低层控制器同款保护）。如实说停在哪、前面还剩多远。
        if r["reason"] == "braked":
            if moved < C.BRAKE_ZERO_MOVE_M:      # 一开始就贴着东西，一步都迈不出去
                self._last_event = f"前面只剩 {r['front_m']:.2f} 米，没法往前走"
                return {"ok": True,
                        "message": (f"没往前走——正前方只剩 {r['front_m']:.2f} 米，"
                                    f"已经贴到安全距离了，这个朝向走不了。"),
                        "data": r}
            self._last_event = f"往前走了 {moved:.2f} 米，前面太近主动停住了"
            return {"ok": True,
                    "message": (f"往前走了 {moved:.2f} 米就停住了{note}——正前方只剩 "
                                f"{r['front_m']:.2f} 米，再走就撞上了，我按安全距离停下站住。"),
                    "data": r}
        # 撞墙/被家具挡住：闭环里已判出"卡住"，或者实际位移远不及目标
        if r["reason"] == "stalled" or moved < capped * C.STUCK_MIN_RATIO:
            self._last_event = f"往前走被挡住，只走了 {moved:.2f} 米"
            # ⛔ 只报事实，不出主意：接下来该转向还是后退，是大脑看画面决定的事。
            # （2026-07-26 审计删掉了原先那句"建议先转个方向再走"——世界替大脑做了决策。）
            return {"ok": True,
                    "message": f"往前只走了 {moved:.2f} 米就走不动了{note}——前面被墙或家具挡住了。",
                    "data": r}
        self._last_event = f"往前走了 {moved:.2f} 米"
        return {"ok": True, "message": f"往前走了 {moved:.2f} 米{note}。", "data": r}

    def _turn(self, degrees: float, sign: int, _progress=None) -> dict:
        if degrees <= 0:
            return {"ok": False, "message": "要转的角度得是正数。"}
        capped = min(degrees, C.MAX_TURN_DEG)
        note = "" if capped == degrees else f"（你要求 {degrees:g} 度，一次最多 {C.MAX_TURN_DEG:g} 度）"
        side = "左" if sign > 0 else "右"
        if _progress:
            _progress(C.PROGRESS_START, f"开始向{side}转 {capped:g} 度…")
        r = self.sim.drive_turn(capped, sign)   # 闭环：转到实测角度达标为止
        turned = abs(r["turned_deg"])
        if r["fallen"]:
            self._last_event = f"向{side}转的时候摔倒了"
            return {"ok": False, "message": f"糟糕，转身时摔倒了（只转了 {turned:.0f} 度）。", "data": r}
        self._last_event = f"向{side}转了 {turned:.0f} 度"
        return {"ok": True, "message": f"向{side}转了 {turned:.0f} 度{note}。", "data": r}

    # ---------------------------------------------------------------- 上帝视角（只给人看）
    def status(self) -> dict:
        """世界真值：机器人在哪、在哪间屋、有没有摔。**绝不进 AWI 观测**，只供人类页与验收使用。"""
        x, y, yaw = self.sim.pose()
        room = L.room_at(x, y)
        return {
            "pose": {"x": round(x, 3), "y": round(y, 3), "heading_deg": round(math.degrees(yaw) % 360.0, 1)},
            "room_key": room,
            "room_label": L.room_label(room),
            "fallen": self.sim.fallen(),
            "tilt_deg": round(math.degrees(self.sim.tilt()), 1),
            "policy": self.sim.policy_path,
        }

    def reset(self) -> dict:
        self.sim.reset()
        self._last_event = "（刚被放回出生点）"
        return {"ok": True, "message": "机器人已放回出生点。"}
