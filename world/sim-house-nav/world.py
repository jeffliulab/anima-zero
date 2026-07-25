"""sim-house-nav 世界对象 —— 实现 AWI 三件事：capabilities() / observe() / invoke()。

这个世界 = 一间三室住宅 + 一只会用真实步态走路的 Go2，狗头上一只前视相机。
ANIMA 只能【看画面】+【发导航原语】，靠自己认出身处哪间屋、决定往哪走。

⛔ 给大脑的观测里**绝不含**狗的坐标、房间名、屋子地图——那是世界的上帝视角真值（走 /status，
   只给人看、用于验收）。房间必须靠看画面认出来，这正是本 demo 要考的能力。
   给的是真实机器人身上本来就有的东西：相机画面 + IMU 朝向 + 自身是否摔倒。
"""
from __future__ import annotations

import math

import config as C
import importlib.util as _ilu
import os as _os
_spec = _ilu.spec_from_file_location(
    "domus_layout", _os.path.join(C.DOMUS_ROOT, C.DOMUS_SCENE, "layout.py"))
L = _ilu.module_from_spec(_spec); _spec.loader.exec_module(L)   # Domus 场景的布局定义
from sim import HouseSim

# 世界说明书（= MCP prompt "guidance"）：世界自我介绍怎么跟它打交道。
# 让大脑保持纯净通用——不为这个世界在大脑里写死任何逻辑，改由世界自述、大脑读了就懂。
GUIDANCE = (
    "我是「屋子导航」世界：一间住宅里有一只四足机器狗（宇树 Go2），你通过它的**头部前视相机**看世界。\n"
    "\n"
    "【你能看到什么】每次感知给你一张狗当前看到的画面，外加它的朝向（IMU 罗盘角度）和是否摔倒。\n"
    "我**不会**告诉你狗在什么坐标、在哪个房间、屋子长什么样——这些要你自己看画面判断。\n"
    "\n"
    "【这是一套大平层住宅（场景代号 Domus01），靠家具认房间】\n"
    "· 玄关：入户大门、鞋柜、换鞋凳、挂衣板、端景台上一只插花的花瓶，地面是白色大理石；\n"
    "· 客厅：转角大沙发正对电视墙（大屏+电视柜）、圆地毯、圆茶几（上面有书和茶盘）、落地灯、绿植；\n"
    "· 餐厅：长餐桌配六把椅子、餐边柜；与客厅完全打通、与开放式西厨中岛（配两把吧椅）相连；\n"
    "· 中厨：封闭式，灶台带灶眼、抽油烟机、烤箱门、水槽、大冰箱、备餐台，地面白瓷砖；\n"
    "· 主卧：双人大床（两个枕头+床头板）、两侧床头柜配台灯、床尾凳、单人沙发椅；\n"
    "· 衣帽间：两侧通顶衣柜挂满衣服、中央岛柜；\n"
    "· 主卫：**独立浴缸**、双台盆大镜子、玻璃隔断淋浴间、马桶，深色瓷砖地；\n"
    "· 次卧：单人床（一个枕头）、小书桌、衣柜；\n"
    "· 客卫：马桶、洗手台配镜子、玻璃淋浴间；\n"
    "· 小孩房：儿童床（橙色被子）、书桌配彩色椅子、玩具架和玩具箱、地上一个球，还带儿童浴缸；\n"
    "· 洗衣房：洗衣机和烘干机（并排两台圆窗白电器）、水槽、置物架、脏衣篮；\n"
    "· 过道：狭长通道，两侧墙上挂画、边柜、绿植，好几扇门开在两边。\n"
    "各个房间的墙色和地面材质也不一样，可以一并作为判断依据。\n"
    "\n"
    "【你能做什么】四个动作，地位并列：**往前走一段**、**原地左转**、**原地右转**、**环视一圈**。\n"
    "前三个让狗动起来；环视是一次把四周看清楚——我带着狗自转一圈、沿途拍好几张，下一次感知"
    "一起给你。到了新地方、或者被挡住想找出路，用环视比你自己「转一下看一眼」来回几趟省事得多。\n"
    "狗是靠学出来的步态真的迈腿走路，\n"
    "所以结果不会分毫不差——我会如实告诉你**实际**走了多远、转了多少度。撞到墙或家具会走不动，\n"
    "这时我会明说「被挡住了」，你要据此改变策略（比如先转个方向再走）。\n"
    "\n"
    "【怎么找路】屋子里有门洞连通房间。看不清就先转身环视一圈；要去某个房间，先判断当前在哪、\n"
    "哪个方向可能通向目标，再一步步走过去、每走一步重新看画面确认。走错了就退回来换个方向。\n"
    "\n"
    "【找一个房间是一件完整的事，一口气做完】你第一次进这间屋子时并不知道各个房间在哪——\n"
    "这很正常，那就**去找**：一间一间看过去，靠常识判断哪个方向更可能（比如厨房多半挨着餐厅）。\n"
    "**别走几步就停下来问用户**——一直找到为止。两种情况才收尾：**找到了**（真的走进了目标房间），\n"
    "或者**把能去的地方都看遍了仍然没有**（这时如实说没找到，别硬撑也别假装找到了）。\n"
    "⚠️ **每探完一处就把进度写进你的核心任务**（比如「找厨房：客厅、主卧、过道已看过，没有」）——\n"
    "找一圈要走几十步，早先看过哪几间屋会随对话变长滑出你的视野，只有核心任务不会丢。\n"
    "不写的话你会绕回已经看过的房间，白费力气还判断不出「是不是已经找遍了」。\n"
    "\n"
    "【什么才算「到了」某个房间——看见就算到】**你能清楚看见目标房间了，就算到了**，\n"
    "不必非得整个身子走进去。站在门口望进厨房、看清了灶台和烤箱，这就算找到厨房了。\n"
    "但「看见」要是**真看清**，不是猜：得能说出你看到了这个房间的哪几件标志物\n"
    "（比如厨房＝灶眼／抽油烟机／烤箱的黑玻璃门／不锈钢洗碗机门／落地大冰箱；\n"
    "卧室＝床和床头柜；客厅＝沙发正对电视墙）。只看到一片说不清是什么的柜门或白墙，\n"
    "那还不算——再走近点、或者环视一圈看清楚了再说。\n"
    "地面材质也可以当辅助线索（客厅深色木地板／厨房浅色瓷砖／卧室浅木色／玄关白色大理石），\n"
    "但它只是佐证，**认出标志物才是主要判据**。\n"
)


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
        │ look_around     原地转一圈拍一组照片    views 3~8       不会（转完回到原朝向）│
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
                        f"让机器狗朝当前正前方走一段距离（米）。最多一次 {C.MAX_MOVE_M:g} 米。"
                        "狗用真实步态行走，实际距离会有出入；撞上墙或家具会提前停下，我会如实告诉你。"),
                    "kind": "tool",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "meters": {
                                "type": "number",
                                "description": f"想往前走多远（米），0 到 {C.MAX_MOVE_M:g}",
                                "default": 1.0,
                            },
                        },
                        "required": ["meters"],
                    },
                },
                {
                    "name": "turn_left",
                    "description": (
                        f"机器狗原地向左（逆时针）转一个角度。最多一次 {C.MAX_TURN_DEG:g} 度。"
                        "转完站定，方便你重新看画面。"),
                    "kind": "tool",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "degrees": {
                                "type": "number",
                                "description": f"向左转多少度，0 到 {C.MAX_TURN_DEG:g}",
                                "default": 45.0,
                            },
                        },
                        "required": ["degrees"],
                    },
                },
                {
                    "name": "turn_right",
                    "description": (
                        f"机器狗原地向右（顺时针）转一个角度。最多一次 {C.MAX_TURN_DEG:g} 度。"
                        "转完站定，方便你重新看画面。"),
                    "kind": "tool",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "degrees": {
                                "type": "number",
                                "description": f"向右转多少度，0 到 {C.MAX_TURN_DEG:g}",
                                "default": 45.0,
                            },
                        },
                        "required": ["degrees"],
                    },
                },
                {
                    "name": "look_around",
                    "description": (
                        "原地转一圈环视四周：我会带着狗**逆时针转满 360 度**，沿途等距拍几张照片，"
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
                },
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

    # ---------------------------------------------------------------- 动作
    def invoke(self, name: str, *, _progress=None, **args) -> dict:
        if name == "move_forward":
            return self._move_forward(float(args.get("meters", 1.0)), _progress)
        if name == "turn_left":
            return self._turn(float(args.get("degrees", 45.0)), +1, _progress)
        if name == "turn_right":
            return self._turn(float(args.get("degrees", 45.0)), -1, _progress)
        if name == "look_around":
            return self._look_around(int(args.get("views", C.SWEEP_VIEWS)), _progress)
        return {"ok": False, "message": f"这个世界没有「{name}」这个动作。"}

    def _look_around(self, views: int, _progress=None) -> dict:
        n = max(C.SWEEP_VIEWS_MIN, min(views, C.SWEEP_VIEWS_MAX))
        note = "" if n == views else f"（你要求 {views} 张，我按 {C.SWEEP_VIEWS_MIN}~{C.SWEEP_VIEWS_MAX} 张的范围取了 {n}）"
        if _progress:
            _progress(0.1, f"开始环视，转一圈拍 {n} 张…")
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
            _progress(0.1, f"开始往前走 {capped:g} 米…")
        r = self.sim.drive_distance(capped)     # 闭环：走到实测位移达标为止
        moved = r["moved_m"]
        if r["fallen"]:
            self._last_event = "刚才往前走的时候摔倒了"
            return {"ok": False, "message": f"糟糕，走的过程中摔倒了（只挪了 {moved:.2f} 米）。", "data": r}
        # 撞墙/被家具挡住：闭环里已判出"卡住"，或者实际位移远不及目标
        if r["reason"] == "stalled" or moved < capped * C.STUCK_MIN_RATIO:
            self._last_event = f"往前走被挡住，只走了 {moved:.2f} 米"
            return {"ok": True,
                    "message": (f"往前只走了 {moved:.2f} 米就走不动了{note}——前面大概被墙或家具挡住了。"
                                f"建议先转个方向再走。"),
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
            _progress(0.1, f"开始向{side}转 {capped:g} 度…")
        r = self.sim.drive_turn(capped, sign)   # 闭环：转到实测角度达标为止
        turned = abs(r["turned_deg"])
        if r["fallen"]:
            self._last_event = f"向{side}转的时候摔倒了"
            return {"ok": False, "message": f"糟糕，转身时摔倒了（只转了 {turned:.0f} 度）。", "data": r}
        self._last_event = f"向{side}转了 {turned:.0f} 度"
        return {"ok": True, "message": f"向{side}转了 {turned:.0f} 度{note}。", "data": r}

    # ---------------------------------------------------------------- 上帝视角（只给人看）
    def status(self) -> dict:
        """世界真值：狗在哪、在哪间屋、有没有摔。**绝不进 AWI 观测**，只供人类页与验收使用。"""
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
        return {"ok": True, "message": "机器狗已放回出生点。"}
