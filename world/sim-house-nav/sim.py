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

import numpy as np

os.environ.setdefault("MUJOCO_GL", "egl")   # 无头渲染（服务器上没有显示器）
import mujoco  # noqa: E402

import config as C  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
SCENE_PATH = os.path.join(C.DOMUS_ROOT, C.DOMUS_SCENE, "house.xml")
POLICY_DIR = os.path.join(C.DOMUS_ROOT, "policies", "go2-velocity-flat")

# 观测项拼接顺序 —— 与训练侧 ObservationsCfg.PolicyCfg 的声明顺序一一对应。
# （Isaac 的 ObsGroup 按声明顺序拼接，contract.json 会带上这份顺序供核对。）
TERM_ORDER = ("base_ang_vel", "projected_gravity", "velocity_commands",
              "joint_pos_rel", "joint_vel_rel", "last_action")


def _wrap(a: float) -> float:
    """把角度差收进 (-π, π]，免得 ±180° 环绕时算出个假的巨大差值。"""
    return (a + math.pi) % (2 * math.pi) - math.pi


class Contract:
    """训练侧口径的机器可读契约（关节序/默认站姿/增益/缩放/时序）。由 dump_contract.py 生成。"""

    def __init__(self, path: str):
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"找不到策略契约 {path}。\n"
                f"它必须由 dump_contract.py 从活的 Isaac 训练环境导出——"
                f"关节顺序和增益绝不能手写猜测（G1 sim2sim 的血泪教训）。")
        d = json.load(open(path, encoding="utf-8"))
        self.joint_names: list[str] = d["joint_names"]          # Isaac 侧顺序（策略输入输出都按它）
        self.default_jpos = np.asarray(d["default_joint_pos"], np.float64)
        self.scales: dict = d["term_scales"]                    # 各观测项缩放
        self.action_scale = float(d["action"]["scale"])
        self.policy_dt = float(d["timing"]["policy_dt_s"])
        self.gains: dict = d["gains"]                           # 关节名 → {kp, kd, effort_limit}
        order = d.get("term_order")
        if order and tuple(order) != TERM_ORDER:
            raise ValueError(f"契约里的观测项顺序 {order} 与本部署器的 {TERM_ORDER} 不一致——"
                             f"训练配置改过了，拼装器必须同步更新，绝不能带着错位跑。")


class HouseSim:
    """屋子 + 会走路的 Go2。一个实例 = 一个持续运行的仿真。"""

    def __init__(self, policy_path: str = "", contract_path: str = ""):
        self.model = mujoco.MjModel.from_xml_path(SCENE_PATH)
        self.data = mujoco.MjData(self.model)
        self.model.opt.timestep = C.PHYSICS_DT

        self.contract = Contract(contract_path or self._find(C.CONTRACT_PATH, "contract.json"))
        self._load_policy(policy_path or self._find(C.POLICY_PATH, "policy.onnx"))
        self._build_joint_map()
        self._strip_untrained_joint_effects()

        self.decimation = max(1, int(round(C.CONTROL_DT / C.PHYSICS_DT)))
        self._cmd = np.zeros(3)              # 当前速度指令 (vx, vy, wz)
        self._prev_action = np.zeros(len(self.contract.joint_names), np.float32)
        self._lock = threading.Lock()        # 只保护"写指令/读位姿"这类小状态
        self._frame: bytes | None = None     # 最新一帧 PNG（原子引用；读方不加锁）
        self._frame_rgb = None               # 最新一帧原始像素（给 MJPEG 直播用，省一次解码）
        self._running = False
        self._thread: threading.Thread | None = None
        self._renderer: mujoco.Renderer | None = None

        self.reset()

    # ---------------------------------------------------------------- 初始化零件
    @staticmethod
    def _find(configured: str, default_name: str) -> str:
        """配置里给了就用配置的；否则找 policy/ 下的同名文件。"""
        if configured:
            return configured
        return os.path.join(POLICY_DIR, default_name)

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

    def _strip_untrained_joint_effects(self) -> None:
        """清掉 MuJoCo 模型里训练时并不存在的关节阻尼与库仑摩擦。

        menagerie 的 go2.xml 给关节写了 damping=2 / frictionloss=0.2（面向"手搓控制器"的默认值），
        但训练侧是 **显式 PD**（kd 由策略回路以力矩形式施加、kp/kd 见契约），并没有这些额外阻力。
        留着它们等于给狗腿灌了糖浆：策略输出的力矩被吃掉一大截，步态会走样。
        ⚠️ 与 G1 那次相反：G1 训练侧是隐式 PD，修法是把 kd 放进 dof_damping；Go2 是显式 PD，
        所以这里要**清零** damping，由本部署器自己算 −kd·qd。（两者搞反必然走不动，务必分清。）
        """
        for i in range(len(self.dadr)):
            d = self.dadr[i]
            self.model.dof_damping[d] = 0.0
            self.model.dof_frictionloss[d] = 0.0

    # ---------------------------------------------------------------- 仿真状态
    def reset(self) -> None:
        """把狗放回出生点、站好、清空历史。"""
        import importlib.util  # 延迟 import：布局定义住在 Domus 资产库里
        _spec = importlib.util.spec_from_file_location(
            "domus_layout", os.path.join(C.DOMUS_ROOT, C.DOMUS_SCENE, "layout.py"))
        _L = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_L)
        mujoco.mj_resetData(self.model, self.data)
        x, y = _L.START_POS_XY
        self.data.qpos[0:3] = [x, y, _L.START_HEIGHT]
        yaw = _L.START_YAW
        self.data.qpos[3:7] = [math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2)]
        self.data.qpos[self.qadr] = self.contract.default_jpos
        self.data.qvel[:] = 0.0
        self._prev_action[:] = 0.0
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
        return np.concatenate([np.asarray(frame[k]).ravel() for k in TERM_ORDER]).astype(np.float32)

    def _policy_step(self) -> None:
        obs = self._observation()[None, :]
        action = self._sess.run(None, {self._in_name: obs})[0][0]
        self._prev_action = action.astype(np.float32)
        # 动作 = 相对默认站姿的关节目标（乘 scale 后叠加），与训练侧 JointPositionAction 一致
        target = self.contract.default_jpos + action.astype(np.float64) * self.contract.action_scale
        q = self.data.qpos[self.qadr]
        qd = self.data.qvel[self.dadr]
        tau = self.kp * (target - q) - self.kd * qd      # 显式 PD（Go2 训练侧即显式，见文件头说明）
        tau = np.clip(tau, -self.tau_max, self.tau_max)
        self.data.ctrl[self.act_id] = tau

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
        next_render = 0.0
        render_period = 1.0 / max(1, C.STREAM_FPS)
        t_wall = time.perf_counter()
        while self._running:
            self._policy_step()
            for _ in range(self.decimation):
                mujoco.mj_step(self.model, self.data)
            now = time.perf_counter()
            if now >= next_render:
                self._render_now()
                next_render = now + render_period
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
        self._renderer.update_scene(self.data, camera=C.CAM_NAME)
        rgb = self._renderer.render()
        buf = io.BytesIO()
        Image.fromarray(rgb).save(buf, format="PNG")
        self._frame = buf.getvalue()      # 原子引用赋值：读方无需加锁
        self._frame_rgb = rgb

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
        while time.perf_counter() < t_end:
            if self.fallen():
                reason = "fallen"
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
                "pose": {"x": x1, "y": y1, "yaw_deg": math.degrees(yaw1)}}
