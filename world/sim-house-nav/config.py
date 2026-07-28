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


def _b(name: str, default: bool) -> bool:
    """开关型 env。认 1/true/yes/on（不分大小写），其余一律当关。"""
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------- 场景资产库
# 场景、机器人模型、运动策略都来自一个独立的资产库；当前挂的是
# **alice-house**（开源 MIT，github.com/jeffliulab/alice-house）。
# 那边长期迭代，这里只管把它挂进来——所以路径走配置、不写死。
# ⚠️ 变量名**故意不带库名**（ASSETS 而不是 ALICE）：这个库 2026-07-26 从 Domus 改名成
#    alice-house，那次改名之所以要动世界侧代码，就是因为当初把库名写进了变量名。
DEFAULT_ASSETS_DIR = "alice-house"
ASSETS_ROOT = _s("HOUSENAV_ASSETS_ROOT",
                 os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
                     os.path.dirname(os.path.abspath(__file__))))), DEFAULT_ASSETS_DIR))

# 用哪台机器人（资产库 robots/manifest.py 里的 key，如 go2 / g1）。空 = 清单里的默认那台。
# ⚠️ 换身体要重建整个仿真（换模型、换策略、回出生点），所以它是**开跑前**的配置，
#    不是对话中途能切的东西；网页上的切换走世界的 POST /config，那边会重建。
ROBOT = _s("HOUSENAV_ROBOT", "")

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

# 大脑没填参数时按这个走。⚠️ 必须只有这一处：工具的 JSON schema `default` 与 invoke 的兜底
# 读的是同一个常量——两边各写一个字面量的话，改了一处忘了另一处就会出现"说明书说 1 米、
# 实际走 2 米"这种查不出来的错。（2026-07-26 审计：原先真的是两处各写一遍。）
DEFAULT_MOVE_M = _f("HOUSENAV_DEFAULT_MOVE_M", 1.0)     # 没说走多远时走几米
DEFAULT_TURN_DEG = _f("HOUSENAV_DEFAULT_TURN_DEG", 45.0)  # 没说转多少时转几度

# 环视（look_around）：原地转一圈拍几张。4 张=前/左/后/右，覆盖一圈又不至于太慢；
# 每多一张就多一次转身+等待稳定，时间线性增加。
#
# ⛔ **v1.0 起默认关闭**（Jeff 2026-07-26 拍板，两种身体都关）。两个理由：
#   ① 它建好之后一次实测都没有——v0.9 期间被大脑侧的能力缓存藏了七次实验，
#      从来没上过工具单。留着一个没验过的能力在清单里，等于声称有而实际没验。
#   ② 人形当时不会原地转身，"原地转一圈拍一组"对它就成了走一个直径一米多的圈——
#      两种身体语义不一样，先都不给，看模型只靠转弯 + 激光测距能不能找到房间。
#
# ⚠️ **理由②已于 2026-07-27 失效**：资产库换上新策略后人形能真正原地转了
#    （转 90° 实测 2.30 秒、40°/s、前后漂移 0.06 米），两台的 `turn_vx` 都是 0。
#    **现在只剩理由①还站得住，而拍板的正是它**——一个从没被实测过的能力，不该因为
#    "挡它的另一个理由没了"就自动打开。要开，得拿实测去决定。
# 代码没删（`_look_around` 与 `sweep` 还在，狗那边是能跑的），想开就把这个 env 设成 1。
LOOK_AROUND = _b("HOUSENAV_LOOK_AROUND", False)
SWEEP_VIEWS = _i("HOUSENAV_SWEEP_VIEWS", 4)
SWEEP_VIEWS_MIN = _i("HOUSENAV_SWEEP_VIEWS_MIN", 3)   # 少于 3 张转一圈会有大片盲区
SWEEP_VIEWS_MAX = _i("HOUSENAV_SWEEP_VIEWS_MAX", 8)   # 再多一轮感知塞不下、也太慢

# ---------------------------------------------------------------- 闭环执行
# 学习步态对速度指令的跟踪不是 1:1（实测直线约 83%、转向约 62%），纯按时间开环下发会系统性
# 走不够/转不够、导航一路偏。所以导航原语闭环执行：一边走一边量，达标才停。
CLOSED_LOOP_TIME_FACTOR = _f("HOUSENAV_CL_TIME_FACTOR", 2.5)  # 时间预算 = 理想耗时 × 此系数
CLOSED_LOOP_EXTRA_S = _f("HOUSENAV_CL_EXTRA_S", 1.5)          # 再加这么多秒的固定余量（起步/收尾）
DRIVE_POLL_S = _f("HOUSENAV_DRIVE_POLL_S", 0.02)              # 闭环查询间隔(s)
STALL_EPS = _f("HOUSENAV_STALL_EPS", 0.02)                    # 进展小于此值(米/弧度)视为没长进
STALL_TIMEOUT_S = _f("HOUSENAV_STALL_TIMEOUT_S", 1.5)         # 连续这么久没长进 = 判定卡住(撞墙)

# 动作刚开工时先报一次进度，让网页立刻看到"它动起来了"（值本身没有物理含义，只是进度条起点）。
PROGRESS_START = _f("HOUSENAV_PROGRESS_START", 0.1)
# 关仿真时等后台线程收工的上限；超时就不等了（daemon 线程随主进程一起走）。
SHUTDOWN_JOIN_S = _f("HOUSENAV_SHUTDOWN_JOIN_S", 3.0)

# ---------------------------------------------------------------- 激光测距（"雷达"）
# 机身上一圈水平射线，量各方向能直着走多远。⚠️ 这不是外挂：真机 Go2（Pro/Edu）头上就装着
# 一颗 L1 激光雷达，Unitree 官方低层控制器也自带撞前保护。
# ⛔ 它只提供**距离读数**，不含任何导航智能——往哪走、要不要退回来，全由大脑看画面+读数决定。
LIDAR_RANGE_M = _f("HOUSENAV_LIDAR_RANGE_M", 8.0)   # 量程(m)。超出/无遮挡一律报这个数（屋子跨度就十几米，8m 够用）
LIDAR_Z_OFFSET = _f("HOUSENAV_LIDAR_Z_OFFSET", 0.05)  # 射线高度 = 机身原点往上这么多(m)。跟着机身走，
#                                                       所以狗(约0.38m)和人形(约0.84m)自动各得其所

# 撞前刹车：往前走的过程中盯着正前方一个锥形区域，太近就停下站住。
# ⛔ **只停不拐**——绝不自己侧移或绕行。停下来之后怎么办是大脑的事。
# 刹车线不是一个写死的距离，而是 **量出来的车头长度 + 这个余量**（见 sim.py 的 _measure_front_extent）。
# 车头有多长是机器人的客观事实（Go2 实测约 0.34 m、人形约 0.2 m），能算就不该让人填——
# 填的数会在换模型时悄悄过期；余量才是"我想留多少安全距离"这个人为选择。
BRAKE_MARGIN_M = _f("HOUSENAV_BRAKE_MARGIN_M", 0.20)
BRAKE_CONE_DEG = _f("HOUSENAV_BRAKE_CONE_DEG", 40.0)  # 盯多宽的一个锥（度，左右各一半）
BRAKE_RAYS = _i("HOUSENAV_BRAKE_RAYS", 5)             # 这个锥里打几条射线，取最近的那条
# 刹车时实际位移不到这个数(m)＝"一开始就贴着东西、一步都没迈出去"，回话措辞不一样：
# 说"走了 0.00 米就停住了"听着像它动过，说"这个朝向走不了"才是大脑需要的信息。
BRAKE_ZERO_MOVE_M = _f("HOUSENAV_BRAKE_ZERO_MOVE_M", 0.05)

# 转弯顺带挪的位移超过这个数(m)就在回话里明说。低于它的是步态自然的一点晃动，
# 每次都报反而是噪音（四足狗原地转也会有几厘米的漂移）。
TURN_REPORT_MOVE_M = _f("HOUSENAV_TURN_REPORT_MOVE_M", 0.15)

# ---------------------------------------------------------------- 卡住 / 摔倒判定
STUCK_MIN_RATIO = _f("HOUSENAV_STUCK_MIN_RATIO", 0.35)  # 实际位移不足目标的这个比例 = 判为"被挡住了"
FALL_TILT_RAD = _f("HOUSENAV_FALL_TILT_RAD", 0.8)       # 躯干倾斜超过这个角度 = 摔倒（对齐训练侧终止条件）
FALL_HEIGHT_M = _f("HOUSENAV_FALL_HEIGHT_M", 0.18)      # 躯干高度低于此 = 趴地上了

# ---------------------------------------------------------------- 第三视角（只给人看）
# 从斜后上方跟拍机器人的一路画面，让你像看比赛转播一样看着它在屋里走。
# ⛔⛔ **这一路 ANIMA 绝对看不到**：只走直播端点，绝不进 observe()。
#     大脑的眼睛只有机器人头上那一只——给它上帝视角就等于把这个 demo 要考的能力直接送掉。
#     红线在三处落实：observe() 不碰它、/streams 标 awi=false、tests/test_third_person.py 钉着。
THIRD_PERSON = _b("HOUSENAV_THIRD_PERSON", True)
THIRD_PERSON_W = _i("HOUSENAV_THIRD_PERSON_W", 640)
THIRD_PERSON_H = _i("HOUSENAV_THIRD_PERSON_H", 480)
# 帧率比第一视角低一档：多一路渲染就多一份开销，而"看着它走"不需要那么流畅。
THIRD_PERSON_FPS = _i("HOUSENAV_THIRD_PERSON_FPS", 8)
# 机位：跟在机器人正后方多远、抬高多少（米）。
# ⚠️ 这里是**兜底默认值**——正常情况下由资产库的机器人清单按机器人给
#    （`chase_back_m` / `chase_up_m`）：狗站立约 0.4 m、人形 1.38 m，同一组机位对谁都不合适。
#    清单没写才用下面这组。
# 屋里空间窄，退太远会退到墙里去；1.8 m 大约是"人站在它身后一步半"的距离。
THIRD_PERSON_BACK_M = _f("HOUSENAV_THIRD_PERSON_BACK_M", 2.2)
THIRD_PERSON_UP_M = _f("HOUSENAV_THIRD_PERSON_UP_M", 1.0)
# 被挡住时把镜头拉近到撞点前面这么多（m），以及无论如何不小于这个距离——
# 太近会糊成一团、也会钻进机器人身体里。
THIRD_PERSON_CLEAR_M = _f("HOUSENAV_THIRD_PERSON_CLEAR_M", 0.15)
THIRD_PERSON_MIN_M = _f("HOUSENAV_THIRD_PERSON_MIN_M", 0.8)
# 为什么是这个角度（俯角约 24°）：机位太高会拍成俯视图、满屏地板，看不见它**要往哪走**；
# 太平又会被自己的身体挡住前方。2.2/1.0 这一组能同时看见机器人和它面前那片空间。

# ---------------------------------------------------------------- 相机 / 画面
# ⚠️ 前视相机叫什么名字**不在这儿**：那是机器人的事实，住资产库的 robots/manifest.py
#    的 camera 字段（两台机器人都叫 head_front，但那是巧合，不该在这儿再定一次）。
CAM_W = _i("HOUSENAV_CAM_W", 640)                  # 给大脑看的画面宽
CAM_H = _i("HOUSENAV_CAM_H", 480)                  # 给大脑看的画面高
STREAM_FPS = _i("HOUSENAV_STREAM_FPS", 15)         # 人类页 MJPEG 直播帧率
STREAM_QUALITY = _i("HOUSENAV_STREAM_QUALITY", 70)  # 直播 JPEG 质量（1-100）

# ---------------------------------------------------------------- 物理
PHYSICS_DT = _f("HOUSENAV_PHYSICS_DT", 0.002)      # MuJoCo 物理步长(s)，官方 Unitree 部署配方同值
CONTROL_DT = _f("HOUSENAV_CONTROL_DT", 0.02)       # 策略推理周期(s)=50Hz，与训练侧一致
REALTIME_FACTOR = _f("HOUSENAV_REALTIME_FACTOR", 1.0)  # 1=按真实时间跑（画面才像直播）；调大=加速

# ---------------------------------------------------------------- 服务
# ⚠️ 端口**不在这儿**：它由启动命令决定（`uvicorn server:app --port 8112`），和其余四个世界一致。
#    这里曾有一个 `PORT = 8112`，但没有任何代码读它——设了 `HOUSENAV_PORT` 不会生效，
#    却在 README 的可调项表里写着"服务端口"。**声称有而实际没有**，2026-07-26 死配置扫描抓到，已删。
CORS_ORIGINS = [o.strip() for o in _s("ANIMA_CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
