"""gazebo-chess 世界的可调项集中地（v0.4）。

约定（对齐 anima-zero 各世界做法 + 开发指南「禁止硬编码」）：
- 所有可调值都在这里，用 GZCHESS_* 环境变量给默认值；别的模块从这里取，不要在代码里 inline 魔法数字。
- 世界进程独立运行，**不 import 大脑的 src/config.py**；这是世界自带的配置。
- 域常量（8×8、格名 a-h / 1-8、夹爪固有几何）属「定义」，不算硬编码。

单位：长度米、角度弧度（角度档用度，便于人读，取用时转弧度）。
"""
from __future__ import annotations

import os


def _f(name: str, default: str) -> float:
    return float(os.getenv(name, default))


def _i(name: str, default: str) -> int:
    return int(os.getenv(name, default))


def _deg_list(name: str, default: str) -> list[float]:
    return [float(x) for x in os.getenv(name, default).split(",") if x.strip() != ""]


# ---- 世界标识 / 服务 ----
WORLD_VERSION = os.getenv("GZCHESS_VERSION", "0.4")
PORT = _i("GZCHESS_PORT", "8106")
STREAM_FPS = _i("GZCHESS_STREAM_FPS", "15")          # 人类页实时视频帧率

# ---- 棋盘几何（米；坐标系 = MoveIt 规划帧 `world` = Gazebo 世界帧）----
# 重要：episode 孪生给 base_link 上面焊了个 `world` 链接，MoveIt 规划帧因此是 `world`，
# 和 Gazebo 世界帧、spawn/读位姿同一个系。所以这里所有坐标都按 `world` 帧给（不是 base_link）。
# 机械臂 base 大约在 world 原点正上方一点（底板 z≈0.02），可达性从 base 算。
# 棋盘 40cm 见方、8×8；格名 a-h(列) / 1-8(行) 是域常量。
BOARD_SIZE_M = _f("GZCHESS_BOARD_SIZE_M", "0.40")
BOARD_FILES = 8                                       # 域常量：列 a-h
BOARD_RANKS = 8                                       # 域常量：行 1-8
CELL_M = BOARD_SIZE_M / BOARD_FILES                   # 派生：每格边长（默认 0.05）
BOARD_THICKNESS_M = _f("GZCHESS_BOARD_THICKNESS_M", "0.008")  # 棋盘底板厚度（坐在桌面 z=0 上）
# 棋盘中心在 world 里的位姿（默认摆臂正前方、桌面上）。可达性按格自检，远格够不着就把这个挪近。
# 背景：episode 桌面碰撞体中心 x≈0.35、臂展≈0.43；默认放近一点，保证演示格轻松够得着。
BOARD_ORIGIN_X = _f("GZCHESS_BOARD_ORIGIN_X", "0.28")
BOARD_ORIGIN_Y = _f("GZCHESS_BOARD_ORIGIN_Y", "0.0")
# 棋盘上表面 z（= 棋子底面所在高度）。
# ⚠️ 实测：episode 的 40×80 安装底板(mount_plate)顶在 z=0.02，比薄棋盘高，会把平铺在 z=0.008 的棋盘**挡住**、
# 棋子还会穿过薄板落到底板上。所以把棋盘**架在底板顶上**：板底=底板顶(0.02)，板面=0.02+厚度(0.008)=0.028。
BOARD_ORIGIN_Z = _f("GZCHESS_BOARD_ORIGIN_Z", "0.028")
BOARD_YAW_RAD = _f("GZCHESS_BOARD_YAW_RAD", "0.0")    # 棋盘绕 z 转角：a→h 方向相对 world +x 的夹角

# ---- 棋子尺寸（米）----
# 注意夹爪可夹宽度区间见下（GRIP_*）：抓取点宽度必须落在该区间内，太细夹不住、太粗夹不下。
PIECE_BASE_DIAM_M = _f("GZCHESS_PIECE_BASE_DIAM_M", "0.030")     # 底座直径 ~3cm
PIECE_HEIGHT_M = _f("GZCHESS_PIECE_HEIGHT_M", "0.045")          # 高 ~4.5cm（兵）
PIECE_GRASP_WAIST_M = _f("GZCHESS_PIECE_GRASP_WAIST_M", "0.020")  # 抓取点离棋子底的高度（夹"腰"）
PIECE_GRASP_WIDTH_M = _f("GZCHESS_PIECE_GRASP_WIDTH_M", "0.035")  # 抓取点处棋子宽度（要落在夹爪可夹区间）

# ---- 相机（俯视）----
CAM_HEIGHT_M = _f("GZCHESS_CAM_HEIGHT_M", "0.55")  # 棋盘上方高度（按"拍全盘+留边"反算，见 geometry 注释）
CAM_FOV_RAD = _f("GZCHESS_CAM_FOV_RAD", "1.0")     # 垂直视野（约 57°）
CAM_W = _i("GZCHESS_CAM_W", "1280")
CAM_H = _i("GZCHESS_CAM_H", "720")
CAM_FPS = _i("GZCHESS_CAM_FPS", "15")

# ---- 夹爪（来自 episode 夹爪 xacro 的固有几何，域常量；这里只记录、便于算夹持目标）----
# 手指为 prismatic，joint∈[0, GRIP_STROKE]；joint=0 闭合、=STROKE 张开。
# 两指内面"面对面"间距 = GRIP_FACE_GAP_CLOSED + 2*joint。
#   GRIP_FACE_GAP_CLOSED = 2*(finger_gap0 - finger_y/2) = 2*(0.018-0.005) = 0.026（2.6cm，能夹的最小宽度）
#   全开（joint=STROKE=0.022）= 0.026 + 0.044 = 0.070（7cm，能夹的最大宽度）
# 所以**可夹宽度区间 ≈ [0.026, 0.070] m**。棋子抓取点宽度必须落这里面。
GRIP_FACE_GAP_CLOSED_M = 0.026
GRIP_STROKE_M = 0.022

# ---- 抓取动作（米 / 弧度）----
APPROACH_SAFE_M = _f("GZCHESS_APPROACH_SAFE_M", "0.10")   # 目标格上方安全高度（抬起/接近用）
# 夹住时每根手指的目标位置（joint 值）；据抓取点宽度算：joint=(W - GRIP_FACE_GAP_CLOSED)/2 再留点挤压余量。
# 默认按 PIECE_GRASP_WIDTH=0.035 → (0.035-0.026)/2≈0.0045，挤压到 0.003。可被 env 直接覆盖。
GRIP_CLOSE_M = _f("GZCHESS_GRIP_CLOSE_M", "0.003")
GRIP_OPEN_M = _f("GZCHESS_GRIP_OPEN_M", "0.020")          # 张开放子/接近时的手指位置
PLACE_TOLERANCE_M = _f("GZCHESS_PLACE_TOLERANCE_M", "0.015")  # 落子到位容差 1.5cm

# ---- 找抓取姿态的备用自由度（够不着/会撞时逐档试；0.4 主要用竖直 0°）----
# 接近方向从竖直往外偏的档（度）；末端 joint6 手腕自转的档（度）。
APPROACH_TILT_DEG = _deg_list("GZCHESS_APPROACH_TILT_DEG", "0,15,30,45")
WRIST_ROLL_DEG = _deg_list("GZCHESS_WRIST_ROLL_DEG", "0,45,90,-45,-90")

# ---- ROS / Gazebo 接口名（可配，别在代码里散落写死）----
ARM_GROUP = os.getenv("GZCHESS_ARM_GROUP", "episode_arm")               # MoveIt 规划组(episode1_urdf_1113_moveit SRDF: base_link→link6)
PLANNING_FRAME = os.getenv("GZCHESS_PLANNING_FRAME", "world")           # MoveIt 规划帧（孪生加了 world 链接）
EEF_LINK = os.getenv("GZCHESS_EEF_LINK", "link6")                       # 给 MoveIt 下位姿目标的末端链接
# 末端 link6 原点 → 两指中间抓取点(TCP) 沿夹爪轴的距离（米）。竖直抓时 = link6 下方这么多。
# 约等于 mount(0.012)+base_z(0.024)+finger_z/2(0.0225) ≈ 0.058；先给默认，明天对着仿真校准。
TCP_OFFSET_M = _f("GZCHESS_TCP_OFFSET_M", "0.058")
GZ_WORLD_NAME = os.getenv("GZCHESS_GZ_WORLD", "episode_world")          # Gazebo 世界名
ARM_CONTROLLER = os.getenv("GZCHESS_ARM_CONTROLLER", "episode_arm_controller")
GRIPPER_CONTROLLER = os.getenv("GZCHESS_GRIPPER_CONTROLLER", "gripper_controller")
CAM_IMAGE_TOPIC = os.getenv("GZCHESS_CAM_IMAGE_TOPIC", "/gazebo_chess/overhead/image")
# 俯视相机的朝向（rpy 弧度）：默认 pitch=+90° 让相机 +x 轴朝下(-z)拍。图像上下/左右朝向需对着仿真确认。
CAM_RPY = [float(x) for x in os.getenv("GZCHESS_CAM_RPY", "0,1.5708,0").split(",")]
