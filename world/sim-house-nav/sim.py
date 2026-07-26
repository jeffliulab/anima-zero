"""MuJoCo 仿真 + Go2 步态策略推理 —— 这个世界的"物理"。

职责：
  1. 后台线程持续跑 MuJoCo 物理，并以 50Hz 让 Go2 的**学习步态策略**输出关节动作 → 狗真的迈腿走路；
  2. 对外只暴露"速度指令"接口 `(vx, vy, wz)`：导航原语（往前走/左转）在 world.py 里被翻译成
     "把某个速度指令保持若干秒"，**不是**把狗瞬移或按公式平移；
  3. 同一个线程按固定帧率渲染头部前视相机，写进 `self._frame`（读方原子取引用、不加锁）——
     这是 ANIMA 的 perceive 画面，也是人类页的 MJPEG 直播源。

⛔ 关节顺序 / 增益 / 缩放 / 默认站姿一律从 **contract.json** 现场读（由 dump_contract.py 从活的
   Isaac 训练环境导出），代码里不写死任何一项；缺文件就明确报错，绝不静默填零糊弄过去。
   这条是 G1 sim2sim 用血换来的纪律：照"分组直觉"手写关节序会全程无声错位。

⚠️ 已知简化（如实登记，未偷偷埋）：训练侧 `UnitreeActuator` 带一条力矩-转速曲线（高速时降额），
   本部署器只做 **显式 PD + 恒定力矩上限** 的钳制，没有复刻那条曲线。平地 0.6m/s 巡航几乎不触及
   降额区，实测能稳定行走即认为够用；若日后出现高速失稳，这里是第一个要补的地方。
"""
from __future__ import annotations

import json
import math
import os
import threading
import time
from collections import deque

import numpy as np

os.environ.setdefault("MUJOCO_GL", "egl")   # 无头渲染（服务器上没有显示器）
import mujoco  # noqa: E402

import config as C  # noqa: E402
import scene_assets  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))

# 观测项拼接顺序 —— 与训练侧 ObservationsCfg.PolicyCfg 的声明顺序一一对应。
# （Isaac 的 ObsGroup 按声明顺序拼接，contract.json 会带上这份顺序供核对。）
TERM_ORDER = ("base_ang_vel", "projected_gravity", "velocity_commands",
              "joint_pos_rel", "joint_vel_rel", "last_action")


def _wrap(a: float) -> float:
    """把角度差收进 (-π, π]，免得 ±180° 环绕时算出个假的巨大差值。"""
    return (a + math.pi) % (2 * math.pi) - math.pi


# 激光测距报哪几个方向 —— **域常量，不是配置项**。
# 名字和条数是绑死的：8 个方向正好把 360° 按 45° 切开，也正好对得上人说方向的习惯
# （"正前""左前""正左"…）。改条数就得重编一套名字，不是调个数字的事，所以不做成 env。
# 角度 = 相对机身正前方逆时针的度数。
LIDAR_BEARINGS = (("正前", 0), ("左前", 45), ("正左", 90), ("左后", 135),
                  ("正后", 180), ("右后", 225), ("正右", 270), ("右前", 315))


class Contract:
    """训练侧口径的机器可读契约（关节序/默认站姿/增益/缩放/时序/历史帧数）。

    由训练环境导出（`dump_contract.py`，或 locomotion 项目实验 10 的 reference/contract.json）。
    ⛔ 这里面每一项都是**训练侧的事实**，代码里一律不许手写猜测——G1 sim2sim 用一整天
    诊断换来的纪律：照"分组直觉"手写关节序会全程无声错位。

    两种历史格式的写法（两边都要认，不然换个机器人就崩）：
      · `gains`：关节名 → {kp, kd, effort_limit}（Go2 的 dump_contract.py 输出）
      · `actuators`：按执行器组分，组里几个并列数组（G1 那份 reference 契约的写法）
    """

    def __init__(self, path: str):
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"找不到策略契约 {path}。\n"
                f"它必须由 dump_contract.py 从活的 Isaac 训练环境导出——"
                f"关节顺序和增益绝不能手写猜测（G1 sim2sim 的血泪教训）。")
        d = json.load(open(path, encoding="utf-8"))
        self.raw = d
        self.joint_names: list[str] = d["joint_names"]          # Isaac 侧顺序（策略输入输出都按它）
        self.default_jpos = np.asarray(d["default_joint_pos"], np.float64)
        self.scales: dict = d["term_scales"]                    # 各观测项缩放
        self.action_scale = float(d["action"]["scale"])
        self.policy_dt = float(d["timing"]["policy_dt_s"])
        # 观测要拼几帧历史（旧→新）。契约没写＝1＝只用当前帧。
        self.history = int(d.get("history_length", 1) or 1)
        self.gains = self._read_gains(d)                        # 关节名 → {kp, kd, effort_limit}
        missing = [n for n in self.joint_names if n not in self.gains]
        if missing:
            raise ValueError(f"契约里这些关节没有增益：{missing}。拒绝带着缺项跑。")
        order = d.get("term_order")
        if order and tuple(order) != TERM_ORDER:
            raise ValueError(f"契约里的观测项顺序 {order} 与本部署器的 {TERM_ORDER} 不一致——"
                             f"训练配置改过了，拼装器必须同步更新，绝不能带着错位跑。")

    @staticmethod
    def _read_gains(d: dict) -> dict:
        """两种契约写法都认，出来的形状统一成 关节名 → {kp, kd, effort_limit}。"""
        if "gains" in d:
            return d["gains"]
        if "actuators" not in d:
            raise ValueError("契约里既没有 gains 也没有 actuators，读不出增益，拒绝运行。")
        out: dict = {}
        for grp in d["actuators"].values():
            names = grp["joint_names"]
            for i, n in enumerate(names):
                def pick(arr, i=i):
                    """组里可能给每关节一个值，也可能只给一个值全组共用。"""
                    if not arr:
                        return 0.0
                    return float(arr[i]) if i < len(arr) else float(arr[0])
                out[n] = {"kp": pick(grp.get("stiffness", [])),
                          "kd": pick(grp.get("damping", [])),
                          "effort_limit": pick(grp.get("effort_limit", [])) or 1e9}
        return out


class HouseSim:
    """屋子 + 会走路的 Go2。一个实例 = 一个持续运行的仿真。"""

    def __init__(self, policy_path: str = "", contract_path: str = "", robot_key: str = ""):
        # 这台仿真装的是哪台机器人：模型、策略、相机、力矩怎么发，全从资产库的机器人清单读，
        # ⛔ 代码里不为任何一台机器人写死东西（加第三台只往清单里追加一条）。
        self.robot_key = robot_key or scene_assets.robot_key()
        self.robot = scene_assets.robots().get(self.robot_key)
        self.scene_path = scene_assets.scene_xml_for(self.robot_key)
        self.policy_dir = os.path.join(C.ASSETS_ROOT, self.robot["policy_dir"])

        self.model = mujoco.MjModel.from_xml_path(self.scene_path)
        self.data = mujoco.MjData(self.model)
        self.model.opt.timestep = C.PHYSICS_DT

        self.contract = Contract(contract_path or self._find(C.CONTRACT_PATH, "contract.json"))
        self._load_policy(policy_path or self._find(C.POLICY_PATH, "policy.onnx"))
        self._build_joint_map()
        self._find_root_body()
        self._build_ray_mask()
        self._measure_front_extent()
        self._apply_actuation_mode()

        self.decimation = max(1, int(round(C.CONTROL_DT / C.PHYSICS_DT)))
        self._cmd = np.zeros(3)              # 当前速度指令 (vx, vy, wz)
        self._prev_action = np.zeros(len(self.contract.joint_names), np.float32)
        # 观测历史缓冲：逐项一个队列（旧→新），长度由契约的 history_length 决定。
        self._obs_hist: dict[str, deque] | None = None
        self._lock = threading.Lock()        # 只保护"写指令/读位姿"这类小状态
        self._frame: bytes | None = None     # 最新一帧 PNG（原子引用；读方不加锁）
        self._frame_rgb = None               # 最新一帧原始像素（给 MJPEG 直播用，省一次解码）
        # 第三视角（⛔ 只给人看，绝不进 observe()）：单独一路像素与渲染器。
        self._third_rgb = None
        self._third_renderer: mujoco.Renderer | None = None
        self._third_cam = None
        self._third_opt = None
        self._chase_body = self._find_chase_body()
        # 跟拍机位按机器人取（狗矮人形高，同一组机位对谁都不合适）；清单没写就退回世界的默认值。
        self._chase_offset = (float(self.robot.get("chase_back_m") or C.THIRD_PERSON_BACK_M),
                              float(self.robot.get("chase_up_m") or C.THIRD_PERSON_UP_M))
        self._running = False
        self._thread: threading.Thread | None = None
        self._renderer: mujoco.Renderer | None = None

        self.reset()

    # ---------------------------------------------------------------- 初始化零件
    def _find(self, configured: str, default_name: str) -> str:
        """配置里给了就用配置的；否则找这台机器人自己的 policy 目录（清单里的 policy_dir）。"""
        if configured:
            return configured
        return os.path.join(self.policy_dir, default_name)

    def _load_policy(self, path: str) -> None:
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"找不到步态策略 {path}。先训练并导出 ONNX（见本目录 README 的 Phase A 步骤）。")
        import onnxruntime as ort
        self._sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
        self._in_name = self._sess.get_inputs()[0].name
        self.policy_path = path

    def _build_joint_map(self) -> None:
        """按**名字**建立 Isaac 关节序 ↔ MuJoCo qpos/qvel/actuator 索引的映射。

        ⛔ 绝不假设两边顺序一致：契约实测 Isaac 是**按关节类型分组**
        （FL_hip, FR_hip, RL_hip, RR_hip, FL_thigh…），MuJoCo go2.xml 是**按腿分组**
        （FL 的三个、FR 的三个…）——照位置对齐必然全程错位且不报错。

        ⛔ 执行器**不能按关节名去查**：menagerie 的执行器叫 `FL_hip`，关节叫 `FL_hip_joint`，
        名字对不上时 `mj_name2id` 返回 −1，而 `data.ctrl[−1]` 会把力矩静默写到最后一个执行器上
        ——狗当场瘫掉、还查不出原因（2026-07-25 实测踩过）。正确做法是看**执行器驱动哪个关节**
        （`actuator_trnid`），与命名习惯无关；配不上就当场报错，绝不带着错映射硬跑。
        """
        c = self.contract
        # 先建"关节 id → 执行器 id"的反查表（依据传动目标，不依赖命名）
        joint_to_act: dict[int, int] = {}
        for aid in range(self.model.nu):
            if self.model.actuator_trntype[aid] == mujoco.mjtTrn.mjTRN_JOINT:
                joint_to_act[int(self.model.actuator_trnid[aid, 0])] = aid

        self.qadr, self.dadr, self.act_id = [], [], []
        missing_joint, missing_act = [], []
        for name in c.joint_names:
            jid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, name)
            if jid < 0:
                missing_joint.append(name)
                continue
            aid = joint_to_act.get(jid, -1)
            if aid < 0:
                missing_act.append(name)
                continue
            self.qadr.append(self.model.jnt_qposadr[jid])
            self.dadr.append(self.model.jnt_dofadr[jid])
            self.act_id.append(aid)
        if missing_joint:
            raise ValueError(f"MuJoCo 模型里找不到这些训练侧关节：{missing_joint}。两边本体对不上，不能硬跑。")
        if missing_act:
            raise ValueError(f"这些关节在 MuJoCo 里没有对应执行器：{missing_act}。驱动不了，拒绝带病运行。")
        self.qadr = np.asarray(self.qadr)
        self.dadr = np.asarray(self.dadr)
        self.act_id = np.asarray(self.act_id)
        # 增益按同一顺序展开成向量
        self.kp = np.asarray([c.gains[n]["kp"] for n in c.joint_names], np.float64)
        self.kd = np.asarray([c.gains[n]["kd"] for n in c.joint_names], np.float64)
        self.tau_max = np.asarray([c.gains[n]["effort_limit"] for n in c.joint_names], np.float64)
        # 基座自由关节（读位姿用）
        self.root_qadr = 0   # freejoint 的 qpos 从 0 开始：xyz(3) + quat(4)

    def _find_root_body(self) -> None:
        """找出机器人的根 body = 挂着 free joint 的那个（躯干/骨盆）。

        按**关节类型**找而不是按名字（Go2 叫 base、G1 叫 pelvis，写死名字换个身体就断）。
        场景里只有机器人有 free joint，房子是静态的——找不到或找到多个都当场报错，不猜。
        """
        free = [int(self.model.jnt_bodyid[j]) for j in range(self.model.njnt)
                if self.model.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE]
        if len(free) != 1:
            raise ValueError(
                f"场景里有 {len(free)} 个 free joint，认不出哪个是机器人。"
                f"这个世界的约定是：场景中有且只有机器人是自由体，房子全是静态几何。")
        self._root_body = free[0]

    def _find_chase_body(self) -> int:
        """第三视角跟拍挂在哪个部件上（机器人清单的 `chase_body`，如狗的 base、人形的 torso_link）。
        名字对不上就退回根 body 并告警——跟拍是给人看的，不该因为一个名字写错就让世界起不来。"""
        name = self.robot.get("chase_body") or ""
        bid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, name) if name else -1
        if bid < 0:
            print(f"[warn] 机器人清单里的 chase_body «{name}» 在模型里找不到，第三视角改跟根部件。")
            return self._root_body
        return bid

    def _measure_front_extent(self) -> None:
        """量出机器人**车头有多长**——从机身原点到自身几何最前端的距离(m)。

        为什么要量而不是每台机器人填一个数：刹车距离必须大于车头长度，否则"离墙 0.5 米"
        其实早就贴上去了。这个长度是模型的客观事实（Go2 实测约 0.34 m、人形约 0.2 m），
        能算就不该让人填——填的数会在换模型、改配置时悄悄过期。
        用 `geom_rbound`（MuJoCo 给每个 geom 算好的包围球半径）取保守上界：
        网格件没法精确求投影，包围球会略偏大，而刹车距离**宁可偏大**。
        """
        mujoco.mj_forward(self.model, self.data)
        rot = np.zeros(9)
        mujoco.mju_quat2Mat(rot, self.data.qpos[3:7])
        fwd = rot.reshape(3, 3)[:, 0]           # 机体 +x 在世界系的方向 = 正前方
        origin = self.data.xpos[self._root_body]
        best = 0.0
        for g in range(self.model.ngeom):
            if self.model.body_rootid[self.model.geom_bodyid[g]] != self._root_body:
                continue
            ahead = float(np.dot(self.data.geom_xpos[g] - origin, fwd)) + float(self.model.geom_rbound[g])
            best = max(best, ahead)
        self.front_extent_m = best
        # 刹车线 = 车头长度 + 余量。余量是**世界的选择**（想留多少安全距离），所以走 config；
        # 车头长度是**机器人的事实**，所以量出来。两者相加才是"从机身原点起算的刹车距离"。
        self.brake_stop_m = best + C.BRAKE_MARGIN_M

    def _build_ray_mask(self) -> None:
        """算出「射线只看房子、不看机器人自己」的 geom 分组掩码。

        为什么必须过滤：射线从机身原点往外打，第一个撞上的必然是机器人自己的躯干/腿
        （实测正前方 0.127 m 就打在自己身上）。
        为什么用**分组掩码**而不是"打到自己就跳过去接着打"：实测正前方向连着穿过 6 个自身
        geom 还没出来（躯干盒 + 头部圆柱 + 球 + 前腿 + 视觉网格…），靠固定重试次数根本不可靠。
        分组掩码是一次到位的精确过滤。

        ⛔ 两边分组撞上了就**拒绝启动**，不猜。撞上意味着没法区分"这条射线打到的是墙还是自己
        的胳膊"，带病跑出来的距离读数会让大脑做出错误判断——那比没有雷达更糟。
        （menagerie 惯例本来就分得开：视觉 group 2 / 碰撞 group 3；房子用 0 和 1。）
        """
        root = self._root_body
        is_self = [self.model.body_rootid[self.model.geom_bodyid[g]] == root
                   for g in range(self.model.ngeom)]
        self_groups = {int(self.model.geom_group[g]) for g in range(self.model.ngeom) if is_self[g]}
        world_groups = {int(self.model.geom_group[g]) for g in range(self.model.ngeom) if not is_self[g]}
        clash = self_groups & world_groups
        if clash:
            raise ValueError(
                f"机器人和房子共用了 geom 分组 {sorted(clash)}，激光测距没法把两者分开。\n"
                f"（机器人用 {sorted(self_groups)}，房子用 {sorted(world_groups)}）\n"
                f"请把机器人模型的 geom 分组改成房子没用到的组"
                f"（menagerie 惯例：视觉 group 2、碰撞 group 3）。拒绝带着错读数运行。")
        mask = np.zeros(6, np.uint8)          # MuJoCo 的分组固定 6 个槽
        for g in world_groups:
            if 0 <= g < len(mask):
                mask[g] = 1
        self._ray_mask = mask
        self._ray_gid = np.zeros(1, np.int32)  # mj_ray 的输出槽（复用，免得每次分配）

    def _ray_vec(self, pnt, vec) -> float:
        """从 pnt 沿 vec 打一条射线，返回撞到房子的距离(m)；没撞上返回 -1。

        ⚠️ flg_static 必须为 1：墙和家具都是静态几何体，设 0 的话什么都打不到（实测全返回 -1）。
        掩码把机器人自己排除在外（见 _build_ray_mask）。
        """
        return float(mujoco.mj_ray(self.model, self.data, np.asarray(pnt, np.float64),
                                   np.asarray(vec, np.float64),
                                   self._ray_mask, 1, -1, self._ray_gid))

    def _ray(self, x: float, y: float, z: float, ang: float) -> float:
        """沿世界系**水平**方位角 ang 打一条射线，返回距离(m)。

        没撞上（或超出量程）一律返回量程值——**不返回 -1 这种要调用方去理解的哨兵**，
        对大脑来说"看不到那么远"和"8 米内没东西"是同一件事。
        """
        d = self._ray_vec([x, y, z], [math.cos(ang), math.sin(ang), 0.0])
        return C.LIDAR_RANGE_M if d < 0 else min(float(d), C.LIDAR_RANGE_M)

    def _ray_origin(self) -> tuple[float, float, float, float]:
        """射线的出发点 (x, y, z) 和当前朝向 yaw。高度=机身原点往上一点，跟着机身走——
        所以四足狗和人形各自量在自己合适的高度上，不用为每种身体单独配。"""
        x, y, yaw = self.pose()
        return x, y, float(self.data.qpos[2]) + C.LIDAR_Z_OFFSET, yaw

    def clearances(self) -> dict[str, float]:
        """八个方向各能直着走多远(m)。这是给大脑的**传感器读数**，和 IMU 朝向一样属于
        "真实机器人身上本来就有的东西"。⛔ 不含坐标、不含房间名、不是地图。"""
        x, y, z, yaw = self._ray_origin()
        return {name: round(self._ray(x, y, z, yaw + math.radians(deg)), 2)
                for name, deg in LIDAR_BEARINGS}

    def front_clearance(self) -> float:
        """正前方那个锥形区域里**最近**的障碍距离(m)——撞前刹车用的。

        为什么用锥而不是一条线：一条线会从门框边、桌腿之间穿过去，报"前面很空"，
        然后肩膀撞上去。取锥内最小值才是"我这么宽的身子往前走会不会碰到"。
        （报给大脑的 clearances 则是每个方向**一条**线：那个数字的含义是"朝这个方位直着走
        能走多远"，精确、好理解；两者用途不同，故意不共用。）
        """
        x, y, z, yaw = self._ray_origin()
        n = max(1, C.BRAKE_RAYS)
        half = math.radians(C.BRAKE_CONE_DEG) / 2.0
        offsets = [0.0] if n == 1 else [-half + 2 * half * i / (n - 1) for i in range(n)]
        return min(self._ray(x, y, z, yaw + o) for o in offsets)

    def _apply_actuation_mode(self) -> None:
        """按这台机器人的 `pd_mode` 布置关节阻尼 —— **两种模式搞反了必倒，这是本文件最容易错的地方**。

        两种模式都要清零**库仑摩擦**：模型里的 `frictionloss` 是给"手搓控制器"准备的默认值，
        训练环境里根本不存在，留着等于给腿灌糖浆。区别在 kd（阻尼）由谁施加：

        · `explicit`（显式 PD，**Go2**）——训练侧 kd 就是策略回路以力矩形式施加的。
          所以模型的 `dof_damping` **清零**，部署器自己算 `tau = kp·(q*−q) − kd·qd`。
        · `implicit`（隐式 PD，**G1**）——训练侧 `ImplicitActuatorCfg`，kp/kd 在 PhysX 求解器里
          隐式施加、无条件稳定。所以 kd 要**写进 `dof_damping`** 让 MuJoCo 用半隐式积分去施加，
          力矩只发 `kp·(q*−q)`。
          ⛔ 把 kd 写成外部力矩 `−kd·qd`（当成显式）会让关节速度从第一步就高频振铃
          （位置跟得住、速度差 L2 约 38）→ 策略收到垃圾 jvel 观测 → 约 1 秒倒。
          这是 locomotion 项目 2026-07-24 花一整天诊断出来的真根因，别再试第二遍。

        模式是**训练侧的事实**，契约里没导出，所以住在机器人清单里（`robots/manifest.py`）。
        """
        mode = self.robot.get("pd_mode")
        if mode not in ("explicit", "implicit"):
            raise ValueError(
                f"机器人「{self.robot_key}」的 pd_mode 是 {mode!r}，只认 'explicit' / 'implicit'。"
                f"这一项决定力矩怎么发，猜错了机器人当场倒——拒绝按默认值蒙。")
        self.pd_mode = mode
        for i, d in enumerate(self.dadr):
            self.model.dof_frictionloss[d] = 0.0
            self.model.dof_damping[d] = 0.0 if mode == "explicit" else float(self.kd[i])

    # ---------------------------------------------------------------- 仿真状态
    def reset(self) -> None:
        """把狗放回出生点、站好、清空历史。"""
        _L = scene_assets.layout()
        mujoco.mj_resetData(self.model, self.data)
        x, y = _L.START_POS_XY
        # 出生点(x,y)是**这套房子**的事（住 layout.py）；出生高度是**这台机器人**的事
        # （住 robots/manifest.py：狗 0.445 m、人形 0.80 m）——两者分开，换身体不用改房子。
        self.data.qpos[0:3] = [x, y, float(self.robot["start_height"])]
        yaw = _L.START_YAW
        self.data.qpos[3:7] = [math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2)]
        self.data.qpos[self.qadr] = self.contract.default_jpos
        self.data.qvel[:] = 0.0
        self._prev_action[:] = 0.0
        self._obs_hist = None            # 观测历史重来（下一帧会用当前状态填满，不留上一条命的残影）
        with self._lock:
            self._cmd = np.zeros(3)
        mujoco.mj_forward(self.model, self.data)

    def pose(self) -> tuple[float, float, float]:
        """(x, y, yaw) —— 世界真值，只给 /status 与内部判断用，绝不进大脑观测。"""
        q = self.data.qpos
        w, xq, yq, zq = q[3], q[4], q[5], q[6]
        yaw = math.atan2(2.0 * (w * zq + xq * yq), 1.0 - 2.0 * (yq * yq + zq * zq))
        return float(q[0]), float(q[1]), float(yaw)

    def tilt(self) -> float:
        """躯干与竖直方向的夹角(rad)，判摔倒用。"""
        # 机体 z 轴在世界系里的朝向
        rot = np.zeros(9)
        mujoco.mju_quat2Mat(rot, self.data.qpos[3:7])
        up_z = rot[8]                       # 机体 z 轴的世界 z 分量
        return float(math.acos(max(-1.0, min(1.0, up_z))))

    def fallen(self) -> bool:
        return self.tilt() > C.FALL_TILT_RAD or float(self.data.qpos[2]) < C.FALL_HEIGHT_M

    # ---------------------------------------------------------------- 策略回路
    def _observation(self) -> np.ndarray:
        """拼一帧策略输入。

        **两种格式一套代码**：契约的 `history_length` 说要拼几帧。
        · 1（Go2）＝只用当前帧，各项按 TERM_ORDER 首尾相接；
        · 5（G1 真机格式）＝**逐项**各存 5 帧（旧→新）先拼成块，再把各项的块首尾相接，总维 480。
        ⛔ 顺序是"逐项历史块"而不是"逐帧全量块"——这两种拼法维度一样、值完全不同，
        拼错了策略照跑不报错、走两步就倒。G1 那边是拿金标准 trace 四假设对拍锁定的
        （max|err|=1.8e-08），这里照那个结论实现，不重新发明。
        第一次调用时用当前帧把历史填满（reset 语义），不是拿零去填。
        """
        c = self.contract
        d = self.data
        # 机体系角速度 / 重力方向
        rot = np.zeros(9)
        mujoco.mju_quat2Mat(rot, d.qpos[3:7])
        R = rot.reshape(3, 3)
        # ⛔ MuJoCo 的 free joint：qvel[0:3] 是**世界系**线速度，但 qvel[3:6] 已经是**机体系**
        # 角速度——直接用，**不能**再乘 R.T。
        # 实测教训（2026-07-25）：多转一次时，yaw=0 恰好 R=I 看不出问题，一转到朝西(yaw≈π)
        # x/y 分量整个取反 → 策略收到反向角速度 → 狗站着就被自己拧翻（倾角 170°）。
        # 症状特征值得记住：**只在某些朝向失稳、且误差随偏离 0° 增大 = 多转了一次坐标系**。
        ang_vel_b = d.qvel[3:6]
        grav_b = R.T @ np.array([0.0, 0.0, -1.0])   # 重力是世界系向量，这个才需要转到机体系
        with self._lock:
            cmd = self._cmd.copy()
        s = c.scales
        frame = {
            "base_ang_vel": ang_vel_b * s["base_ang_vel"],
            "projected_gravity": grav_b * s["projected_gravity"],
            "velocity_commands": cmd * s["velocity_commands"],
            "joint_pos_rel": (d.qpos[self.qadr] - c.default_jpos) * s["joint_pos_rel"],
            "joint_vel_rel": d.qvel[self.dadr] * s["joint_vel_rel"],
            "last_action": self._prev_action * s["last_action"],
        }
        frame = {k: np.asarray(v, np.float64).ravel() for k, v in frame.items()}
        if c.history <= 1:
            return np.concatenate([frame[k] for k in TERM_ORDER]).astype(np.float32)
        if self._obs_hist is None:      # 首帧：拿当前帧填满历史，不拿零填
            self._obs_hist = {k: deque([frame[k]] * c.history, maxlen=c.history) for k in TERM_ORDER}
        else:
            for k in TERM_ORDER:
                self._obs_hist[k].append(frame[k])
        return np.concatenate([np.concatenate(list(self._obs_hist[k])) for k in TERM_ORDER]).astype(np.float32)

    def _policy_step(self) -> None:
        obs = self._observation()[None, :]
        action = self._sess.run(None, {self._in_name: obs})[0][0]
        self._prev_action = action.astype(np.float32)
        # 动作 = 相对默认站姿的关节目标（乘 scale 后叠加），与训练侧 JointPositionAction 一致
        target = self.contract.default_jpos + action.astype(np.float64) * self.contract.action_scale
        q = self.data.qpos[self.qadr]
        tau = self.kp * (target - q)
        if self.pd_mode == "explicit":
            # 显式 PD：阻尼这一项由我们自己算成力矩（模型的 dof_damping 已清零）。
            tau = tau - self.kd * self.data.qvel[self.dadr]
        # 隐式 PD 则不加这一项——kd 已经写进 dof_damping，由 MuJoCo 半隐式积分施加。
        # 加了就等于施加两遍阻尼，而且外部那遍会引发高频振铃（见 _apply_actuation_mode）。
        self.data.ctrl[self.act_id] = np.clip(tau, -self.tau_max, self.tau_max)

    # ---------------------------------------------------------------- 后台主循环
    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="housesim")
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=C.SHUTDOWN_JOIN_S)

    def _loop(self) -> None:
        """物理 + 策略 + 渲染，全在这一个线程里（EGL 上下文有线程亲和性，渲染不能跨线程）。"""
        self._renderer = mujoco.Renderer(self.model, C.CAM_H, C.CAM_W)
        if C.THIRD_PERSON:
            # ⚠️ 必须在**这个线程**里建：EGL 上下文有线程亲和性，跨线程渲染会崩。
            self._third_renderer = mujoco.Renderer(self.model, C.THIRD_PERSON_H, C.THIRD_PERSON_W)
            self._third_cam = mujoco.MjvCamera()
            self._third_cam.type = mujoco.mjtCamera.mjCAMERA_FREE
            self._third_opt = mujoco.MjvOption()
            # 关掉天花板那一组：从斜上方看进去否则只有一片屋顶。
            self._third_opt.geomgroup[scene_assets.layout().CEILING_GROUP] = 0
        next_render = 0.0
        next_third = 0.0
        render_period = 1.0 / max(1, C.STREAM_FPS)
        third_period = 1.0 / max(1, C.THIRD_PERSON_FPS)
        t_wall = time.perf_counter()
        while self._running:
            self._policy_step()
            for _ in range(self.decimation):
                mujoco.mj_step(self.model, self.data)
            now = time.perf_counter()
            if now >= next_render:
                self._render_now()
                next_render = now + render_period
            if self._third_renderer is not None and now >= next_third:
                self._render_third_person()
                next_third = now + third_period
            # 按真实时间推进，让画面像直播（REALTIME_FACTOR 可加速）
            t_wall += C.CONTROL_DT / max(1e-6, C.REALTIME_FACTOR)
            lag = t_wall - time.perf_counter()
            if lag > 0:
                time.sleep(lag)
            else:
                t_wall = time.perf_counter()   # 落后了就重新对表，不追赶补偿

    def _render_now(self) -> None:
        import io
        from PIL import Image
        self._renderer.update_scene(self.data, camera=self.robot["camera"])
        rgb = self._renderer.render()
        buf = io.BytesIO()
        Image.fromarray(rgb).save(buf, format="PNG")
        self._frame = buf.getvalue()      # 原子引用赋值：读方无需加锁
        self._frame_rgb = rgb

    def _render_third_person(self) -> None:
        """渲染第三视角跟拍。⛔⛔ 这一路只写进 `_third_rgb`，**绝不进 observe()**。

        怎么跟拍：用自由相机，每帧把 lookat 放到机器人身上、机位放到它斜后上方——
        位置跟着走，朝向固定在世界系（不跟着机身摇），画面才不会因为步态起伏一直晃。
        天花板那一组几何体关掉：不然从斜上方看进去只有一片屋顶（资产库早就把天花板单独归了组，
        就是为了这种俯视需求）。
        """
        cam = self._third_cam
        pos = self.data.xpos[self._chase_body]
        _x, _y, yaw = self.pose()
        cam.lookat[:] = pos
        # distance/azimuth/elevation 是"绕着 lookat 转"的语义：方位角跟着机身朝向走，
        # 相机就永远待在它**背后**（不然狗一转弯就变成拍脸）。
        back_m, up_m = self._chase_offset
        want = math.hypot(back_m, up_m)
        # ⚠️ 方位角就是机身朝向，**不要 +180**。MuJoCo 自由相机的 azimuth 描述的是
        # "相机往哪个方向看"，不是"相机在哪个方位"——加了 180 就跑到正前方去拍脸了。
        # 判据（别靠推理，看画面）：跟拍的背景应该和第一视角看到的是同一片东西。
        # 2026-07-26 实测：加 180 时背景是身后的柜子，不加时背景是它正对着的两个门洞 ✅。
        cam.azimuth = math.degrees(yaw)
        cam.elevation = -math.degrees(math.atan2(up_m, back_m))
        # 被墙或家具挡住就把镜头拉近——屋里空间窄，机位常常正好落在一件家具后面，
        # 不拉近的话画面里就是一块柜子背板。（游戏里第三人称相机的标准做法；这里正好复用
        # 已有的射线机制：从机器人往机位方向打一条，撞上了就退到撞点前面一点。）
        el = math.radians(cam.elevation)
        az = math.radians(cam.azimuth)
        back = np.array([-math.cos(el) * math.cos(az), -math.cos(el) * math.sin(az),
                         math.sin(-el)])          # 由 lookat 指向机位的单位向量
        hit = self._ray_vec(pos, back)
        cam.distance = max(C.THIRD_PERSON_MIN_M, min(want, hit - C.THIRD_PERSON_CLEAR_M)) \
            if hit > 0 else want
        self._third_renderer.update_scene(self.data, camera=cam, scene_option=self._third_opt)
        self._third_rgb = self._third_renderer.render()

    def third_person_jpeg(self) -> bytes | None:
        """第三视角的最新一帧（JPEG）。只给人类页的直播用。"""
        rgb = self._third_rgb
        if rgb is None:
            return None
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.fromarray(rgb).save(buf, format="JPEG", quality=C.STREAM_QUALITY)
        return buf.getvalue()

    def frame_png(self) -> bytes | None:
        return self._frame

    def frame_jpeg(self) -> bytes | None:
        rgb = self._frame_rgb
        if rgb is None:
            return None
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.fromarray(rgb).save(buf, format="JPEG", quality=C.STREAM_QUALITY)
        return buf.getvalue()

    # ---------------------------------------------------------------- 给导航原语用的执行接口
    def drive(self, vx: float, vy: float, wz: float, seconds: float) -> dict:
        """下发一个速度指令并保持若干秒（开环），然后停下站定。主要给标定/测试用。

        导航原语走下面的**闭环**版本；开环留着是因为测速度跟踪能力时需要它。
        """
        return self._drive_until(vx, vy, wz, seconds, target_kind=None, target=0.0)

    def drive_distance(self, meters: float) -> dict:
        """往前走到**实测**净位移达标为止（闭环）。撞墙走不动会提前收手并如实说明。"""
        # 超时余量：按命令速度算的理想耗时再放宽一倍多（步态跟踪不可能 100%，但也不能无限等）
        budget = meters / max(1e-6, C.WALK_SPEED) * C.CLOSED_LOOP_TIME_FACTOR + C.CLOSED_LOOP_EXTRA_S
        return self._drive_until(C.WALK_SPEED, 0.0, 0.0, budget, target_kind="dist", target=meters)

    def drive_turn(self, degrees: float, sign: int) -> dict:
        """原地转到**实测**转角达标为止（闭环）。sign: +1 左转 / −1 右转。"""
        rad = math.radians(degrees)
        budget = rad / max(1e-6, C.TURN_RATE) * C.CLOSED_LOOP_TIME_FACTOR + C.CLOSED_LOOP_EXTRA_S
        return self._drive_until(0.0, 0.0, sign * C.TURN_RATE, budget, target_kind="yaw", target=rad)

    def sweep(self, n_views: int) -> tuple[list[tuple[str, bytes]], dict]:
        """原地转一圈，沿途等距拍 n 张照片，回 [(方位名, png), …] + 执行情况。

        为什么要有这个：狗只会「前进/左转/右转」，想看看四周就得转一次拍一张、来回四趟——
        每趟都是一次完整的「世界渲染→发给大脑→大脑思考→回一个动作」，几秒钟加一次模型调用。
        环视把这四趟并成一次动作，由世界自己转、自己拍，一次把全景交给大脑。
        ⛔ 它只是个"拍照姿势"，不含任何导航智能：往哪走、这是哪间屋，仍然全由大脑看图判断。
        """
        step_deg = 360.0 / max(1, n_views)
        shots: list[tuple[str, bytes]] = []
        turned_total = 0.0
        fallen = False
        _x, _y, yaw0 = self.pose()
        for i in range(n_views):
            png = self.frame_png()
            if png:
                # 方位名用【相对起始朝向】转过的角度，不用罗盘绝对角——大脑要的是
                # "这张是我左手边/背后"，相对量才好理解。
                shots.append((f"左转{round(turned_total):d}度", png))
            # ⚠️ 拍完最后一张**还要再转一次**才转满 360° 回到原朝向。
            # （少转这一下的话，4 张只转 270°，狗结束时朝向偏了 90°——工具说明里"转完回到
            #   原朝向"就成了假话。2026-07-25 实测 heading_drift=-87° 抓到过一次。）
            r = self.drive_turn(step_deg, +1)        # 统一左转（逆时针）扫一圈
            turned_total += abs(r["turned_deg"])
            if r["fallen"]:
                fallen = True
                break
        _x2, _y2, yaw1 = self.pose()
        return shots, {"n_views": len(shots), "turned_deg": round(turned_total, 1),
                       "fallen": fallen,
                       "heading_drift_deg": round(math.degrees(_wrap(yaw1 - yaw0)), 1)}

    def _drive_until(self, vx: float, vy: float, wz: float, budget_s: float,
                     target_kind: str | None, target: float) -> dict:
        """下发速度指令，直到【实测量达标】/【超时】/【卡住】/【摔倒】其一发生。

        为什么闭环：学习步态对速度指令的跟踪不是 1:1（实测直线 ~83%、转向 ~62%），
        纯按时间开环下发会系统性走不够、转不够，导航就会一路偏。真实机器人导航栈同样是
        把速度指令闭在里程计/IMU 上的——这不是"作弊修正"，狗依旧靠真实步态迈腿走，
        我们只是决定**什么时候停止下发**。实际达成量照实返回，绝不把命令值抄成结果。
        """
        x0, y0, yaw0 = self.pose()
        with self._lock:
            self._cmd = np.array([vx, vy, wz], float)

        acc_yaw = 0.0            # 累计转角（逐步累加，避免 ±180° 环绕出错）
        prev_yaw = yaw0
        best_progress = 0.0      # 迄今最好成绩，用于判"卡住"
        t_stall = time.perf_counter()
        t_end = time.perf_counter() + max(0.0, budget_s)
        reason = "budget"
        braked_at = 0.0          # 刹车时正前方还剩多远（如实报给大脑）
        while time.perf_counter() < t_end:
            if self.fallen():
                reason = "fallen"
                break
            # 撞前刹车：只在**往前走**时管，原地转身不管（转身本来就是贴着东西也能做的事）。
            # ⛔ 只停不拐：停下来站住，绝不自己侧移绕行——往哪走是大脑的决定。
            if target_kind == "dist":
                front = self.front_clearance()
                if front < self.brake_stop_m:
                    braked_at, reason = front, "braked"
                    break
            x, y, yaw = self.pose()
            acc_yaw += math.atan2(math.sin(yaw - prev_yaw), math.cos(yaw - prev_yaw))
            prev_yaw = yaw
            progress = (math.hypot(x - x0, y - y0) if target_kind == "dist"
                        else abs(acc_yaw) if target_kind == "yaw" else 0.0)
            if target_kind and progress >= target:
                reason = "reached"
                break
            # 卡住判定：一段时间内毫无长进（撞墙时就是这样）
            if progress > best_progress + C.STALL_EPS:
                best_progress = progress
                t_stall = time.perf_counter()
            elif target_kind and time.perf_counter() - t_stall > C.STALL_TIMEOUT_S:
                reason = "stalled"
                break
            time.sleep(C.DRIVE_POLL_S)

        with self._lock:
            self._cmd = np.zeros(3)
        # 站定：让姿态收敛，免得刚停下就拍到一张糊的/歪的
        time.sleep(max(0.0, C.STEP_SETTLE_S))
        x1, y1, yaw1 = self.pose()
        acc_yaw += math.atan2(math.sin(yaw1 - prev_yaw), math.cos(yaw1 - prev_yaw))
        return {"moved_m": math.hypot(x1 - x0, y1 - y0),
                "turned_deg": math.degrees(acc_yaw),
                "fallen": self.fallen(),
                "reason": reason,
                "front_m": round(braked_at, 2) if reason == "braked" else None,
                "pose": {"x": x1, "y": y1, "yaw_deg": math.degrees(yaw1)}}
