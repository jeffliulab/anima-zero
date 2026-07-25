"""sim-house-nav 世界的可调项 —— 集中一处，env 可覆盖。

⛔ 世界是独立进程，**不 import 大脑的 config**（脑/身不互相 import 是项目铁律）。
凡是"可能想调"的数字都必须住在这里、带名字带说明，代码里不许出现裸魔法数字。
env 变量一律 `HOUSENAV_` 前缀（对齐 SIMCHESS_ / GZCHESS_ / CAMERA_ 的既有惯例）。
"""
from __future__ import annotations

import os


def _f(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def _i(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _s(name: str, default: str) -> str:
    return os.getenv(name, default)


# ---------------------------------------------------------------- 场景资产（Domus）
# 场景与机器人模型来自独立的资产库 **Domus**（私有仓 github.com/jeffliulab/domus）。
# 那边长期迭代（Domus01/02/03…），这里只管把它挂进来——所以路径走配置、不写死。
DOMUS_ROOT = _s("HOUSENAV_DOMUS_ROOT",
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
                    os.path.dirname(os.path.abspath(__file__))))), "domus"))
DOMUS_SCENE = _s("HOUSENAV_DOMUS_SCENE", "domus01")   # 用哪一套场景

# ---------------------------------------------------------------- 策略与模型
# 训好的 Go2 行走策略（ONNX）。默认找仓内 policy/ 目录；换策略只改这个 env。
POLICY_PATH = _s("HOUSENAV_POLICY", "")          # 空 = 用 policy/ 下的默认文件（见 sim.py 的发现逻辑）
CONTRACT_PATH = _s("HOUSENAV_CONTRACT", "")      # 空 = policy/contract.json

# ---------------------------------------------------------------- 导航原语的"力度"
# ANIMA 发的是"往前走 1 米"这类高层意图，世界把它翻译成给策略的速度指令并保持一段时间。
# ⚠️ 这些不是"假动作"参数：狗真的靠学习步态在跟踪这个速度指令走出去。
WALK_SPEED = _f("HOUSENAV_WALK_SPEED", 0.6)      # 前进时下发的 vx (m/s)。Go2 平地巡航速度，太快易撞墙
TURN_RATE = _f("HOUSENAV_TURN_RATE", 0.8)        # 转向时下发的 wz (rad/s)，约 46°/s
STEP_SETTLE_S = _f("HOUSENAV_STEP_SETTLE_S", 0.6)  # 一个动作结束后原地站定多久，让姿态稳下来再拍照

# 单次原语的上限（防 LLM 一次要求走 50 米把狗开到天涯海角；超限世界会截断并如实告知）
MAX_MOVE_M = _f("HOUSENAV_MAX_MOVE_M", 3.0)      # 一次最多走几米（屋子跨度 8m，3m 够跨半间屋）
MAX_TURN_DEG = _f("HOUSENAV_MAX_TURN_DEG", 180.0)  # 一次最多转多少度

# ---------------------------------------------------------------- 闭环执行
# 学习步态对速度指令的跟踪不是 1:1（实测直线约 83%、转向约 62%），纯按时间开环下发会系统性
# 走不够/转不够、导航一路偏。所以导航原语闭环执行：一边走一边量，达标才停。
CLOSED_LOOP_TIME_FACTOR = _f("HOUSENAV_CL_TIME_FACTOR", 2.5)  # 时间预算 = 理想耗时 × 此系数
CLOSED_LOOP_EXTRA_S = _f("HOUSENAV_CL_EXTRA_S", 1.5)          # 再加这么多秒的固定余量（起步/收尾）
DRIVE_POLL_S = _f("HOUSENAV_DRIVE_POLL_S", 0.02)              # 闭环查询间隔(s)
STALL_EPS = _f("HOUSENAV_STALL_EPS", 0.02)                    # 进展小于此值(米/弧度)视为没长进
STALL_TIMEOUT_S = _f("HOUSENAV_STALL_TIMEOUT_S", 1.5)         # 连续这么久没长进 = 判定卡住(撞墙)

# ---------------------------------------------------------------- 卡住 / 摔倒判定
STUCK_MIN_RATIO = _f("HOUSENAV_STUCK_MIN_RATIO", 0.35)  # 实际位移不足目标的这个比例 = 判为"被挡住了"
FALL_TILT_RAD = _f("HOUSENAV_FALL_TILT_RAD", 0.8)       # 躯干倾斜超过这个角度 = 摔倒（对齐训练侧终止条件）
FALL_HEIGHT_M = _f("HOUSENAV_FALL_HEIGHT_M", 0.18)      # 躯干高度低于此 = 趴地上了

# ---------------------------------------------------------------- 相机 / 画面
CAM_NAME = _s("HOUSENAV_CAM_NAME", "head_front")   # 机体上那只前视相机的名字（见 world/go2.xml）
CAM_W = _i("HOUSENAV_CAM_W", 640)                  # 给大脑看的画面宽
CAM_H = _i("HOUSENAV_CAM_H", 480)                  # 给大脑看的画面高
STREAM_FPS = _i("HOUSENAV_STREAM_FPS", 15)         # 人类页 MJPEG 直播帧率
STREAM_QUALITY = _i("HOUSENAV_STREAM_QUALITY", 70)  # 直播 JPEG 质量（1-100）

# ---------------------------------------------------------------- 物理
PHYSICS_DT = _f("HOUSENAV_PHYSICS_DT", 0.002)      # MuJoCo 物理步长(s)，官方 Unitree 部署配方同值
CONTROL_DT = _f("HOUSENAV_CONTROL_DT", 0.02)       # 策略推理周期(s)=50Hz，与训练侧一致
REALTIME_FACTOR = _f("HOUSENAV_REALTIME_FACTOR", 1.0)  # 1=按真实时间跑（画面才像直播）；调大=加速

# ---------------------------------------------------------------- 服务
PORT = _i("HOUSENAV_PORT", 8112)                   # 世界服务端口（避开 8100/8102/8104/8106/8108）
CORS_ORIGINS = [o.strip() for o in _s("ANIMA_CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
