"""中央配置（脑侧）—— 所有可调数字 / 默认值 / 模型 id / 路径派生 的**单一来源**。

⛔ 禁止硬编码：凡是可调的数字、默认、模型 id、路径，都集中在这里，且**全部 env 可覆盖**；
代码各处从这里读，不再 inline 写死。域常量（棋盘 8×8、FEN 符号、枚举）不在此（那是定义）。

注：棋盘"物理外观"常量（格尺寸/颜色/字号）不放这里——它是**渲染↔视觉两侧必须逐像素一致的共享规格**，
若做成 env 可让两侧分别覆盖、反而会不一致；故保留为各自文件里的命名常量（由 round-trip 测试守一致）。
字体路径属"按机器发现"的东西，放这里做发现式。
"""
from __future__ import annotations

import os
from pathlib import Path


def _i(key: str, default: str) -> int:
    return int(os.getenv(key, default))


def _f(key: str, default: str) -> float:
    return float(os.getenv(key, default))


def _s(key: str, default: str) -> str:
    return os.getenv(key, default)


# ---- 编排器 / 上下文 ----
MAX_STEPS = _i("ANIMA_MAX_STEPS", "8")                   # ReAct 主循环最多转几轮
CONTEXT_TOKEN_BUDGET = _i("ANIMA_CONTEXT_BUDGET", "6000")  # 上下文滑窗 token 预算

# ---- 世界客户端 / 会话 / AWI 日志 ----
# WORLD_TIMEOUT 只管【快速读操作】（capabilities 握手 / perceive）的死线——读操作本该秒回，死线语义正确。
WORLD_TIMEOUT = _f("ANIMA_WORLD_TIMEOUT", "30")
WORLD_PROBE_TIMEOUT = _f("ANIMA_WORLD_PROBE_TIMEOUT", "1.5")
# 世界本地 /status(人类调试台真值)的超时:有的世界现算真值(如 gazebo-chess 抓一段 gz 位姿)比 /health 慢,给它宽一点。
WORLD_STATUS_TIMEOUT = _f("ANIMA_WORLD_STATUS_TIMEOUT", "5")
# ---- 动作(invoke)的「生命迹象」语义（v0.5 wave 0 框架修正）----
# 物理动作可能要几十秒：不对「动作比 X 秒长」判死，而对「X 秒没有任何生命迹象」判失联——
# 世界经 MCP progress 报进度即续命（MCP 规范的 SHOULD-reset，SDK 不做、由 mcp_bridge.run_alive 落地），
# 另设总上限硬闸（有进度也不无限等）。取消响应粒度 = 监督器巡检步长。
WORLD_CONNECT_TIMEOUT = _f("ANIMA_WORLD_CONNECT_TIMEOUT", "5")       # 连上世界 / MCP 握手的死线
WORLD_LIVENESS_TIMEOUT = _f("ANIMA_WORLD_LIVENESS_TIMEOUT", "20")    # 无生命迹象判失联（progress 即续命）
WORLD_INVOKE_HARD_CAP = _f("ANIMA_WORLD_INVOKE_HARD_CAP", "180")     # 单次动作总上限（有进度也不无限等）
BRIDGE_WATCHDOG_POLL_S = _f("ANIMA_BRIDGE_WATCHDOG_POLL_S", "0.25")  # 监督器巡检步长（也是取消响应延迟）
BRIDGE_GRACE_S = _f("ANIMA_BRIDGE_GRACE_S", "5")                     # 外层后备宽限（监督器才是权威，这是安全带）
ENGINE_MCP_TIMEOUT = _f("ANIMA_ENGINE_MCP_TIMEOUT", "15")            # 引擎 server 一次调用的死线（纯计算，秒回）
TITLE_MAX_LEN = _i("ANIMA_TITLE_MAX_LEN", "24")
AWI_LOG_MAXLEN = _i("ANIMA_AWI_LOG_MAXLEN", "400")
AWI_POLL_INTERVAL_S = _f("ANIMA_AWI_POLL_INTERVAL_S", "0.25")

# ---- LLM ----
MAX_TOKENS = _i("ANIMA_MAX_TOKENS", "1024")
OLLAMA_PROBE_TIMEOUT = _f("ANIMA_OLLAMA_PROBE_TIMEOUT", "0.6")
OLLAMA_BASE_URL = _s("OLLAMA_BASE_URL", "http://localhost:11434/v1")
DEFAULT_BRAIN = _s("ANIMA_DEFAULT_BRAIN", "gpt-4.1-nano")
# 模型 id 单一来源（每个可 env 覆盖）
MODEL_OPUS = _s("ANIMA_CLAUDE_OPUS_MODEL", "claude-opus-4-8")
MODEL_HAIKU = _s("ANIMA_CLAUDE_HAIKU_MODEL", "claude-haiku-4-5")
MODEL_GPT = _s("ANIMA_OPENAI_GPT_MODEL", "gpt-5.5")
MODEL_GPT_NANO = _s("ANIMA_OPENAI_NANO_MODEL", "gpt-4.1-nano")
MODEL_QWEN = _s("ANIMA_QWEN3VL_MODEL", "qwen3-vl:8b")

# ---- 对弈行为树 / 对局默认 ----
GAME_TICK_S = _f("ANIMA_GAME_TICK_S", "1.0")
GAME_MAX_FAIL = _i("ANIMA_GAME_MAX_FAIL", "5")              # 发命令(act)连续失败上限
GAME_PERCEIVE_MAX_FAIL = _i("ANIMA_GAME_PERCEIVE_MAX_FAIL", "5")  # 感知(世界异常)失败上限(与 act 分开计)
GAME_EVENT_BUFFER = _i("ANIMA_GAME_EVENT_BUFFER", "500")
GAME_WORLD_TIMEOUT = _f("ANIMA_GAME_WORLD_TIMEOUT", "2.5")  # 对弈专用世界 client 的【读操作】短超时(perceive 要快)。取消响应现靠 invoke 的 _should_abort(粒度=BRIDGE_WATCHDOG_POLL_S)，不再靠短超时兜底
GAME_CANCEL_JOIN_S = _f("ANIMA_GAME_CANCEL_JOIN_S", "3.0")  # manager 停旧 runner 的 join 上限
GAME_RESIGN_EVAL = _i("ANIMA_GAME_RESIGN_EVAL", "-900")    # 我方视角形势评分(厘兵)低于此→倾向认输(约落后一个皇后)
GAME_RESIGN_CONFIRM = _i("ANIMA_GAME_RESIGN_CONFIRM", "3")  # 评分须连续这么多拍都极差才认输(避免兑子瞬间误判)
# 视觉(置信度/多帧确认)
VISION_AMBIGUITY_RATIO = _f("ANIMA_VISION_AMBIGUITY_RATIO", "0.7")  # Lowe 比值:最近/次近 SAD 超此→该格"看不清"
VISION_CONFIRM_FRAMES = _i("ANIMA_VISION_CONFIRM_FRAMES", "2")      # 多帧确认:候选局面连续几帧一致才采信
# 视觉·追踪层(占用+颜色识别器,v0.5 视觉桥第一层;下述默认按 gazebo 绿板/白黑子标定,斜视真帧上可再调)
VISION_OCC_WHITE_THRESH = _i("ANIMA_VISION_OCC_WHITE_THRESH", "150")  # 非绿像素灰度>此→算白子像素
VISION_OCC_BLACK_THRESH = _i("ANIMA_VISION_OCC_BLACK_THRESH", "80")   # 非绿像素灰度<此→算黑子像素
VISION_OCC_GREEN_MARGIN = _i("ANIMA_VISION_OCC_GREEN_MARGIN", "12")   # G 比 R/B 高出这么多→算板面绿
# 判"格上有东西"的门槛：底带里非绿(非板面)像素占比达到此值→有物。子底座(直径3cm/格5cm)在底带
# 的投影约占 1/4 上下，0.12 给一倍余量；低于它=板面为主=空格。
VISION_OCC_OCCUPIED_MIN_FRAC = _f("ANIMA_VISION_OCC_OCCUPIED_MIN_FRAC", "0.12")
VISION_OCC_DOMINANCE = _f("ANIMA_VISION_OCC_DOMINANCE", "0.55")  # 白/黑像素占非绿比须>此才敢判色,否则"看不清"
VISION_OCC_BAND_FRAC = _f("ANIMA_VISION_OCC_BAND_FRAC", "0.45")  # 采样带=格投影靠相机一侧的这部分(子底座在格内、受遮挡最小)
VISION_OCC_MIN_BAND_PX = _i("ANIMA_VISION_OCC_MIN_BAND_PX", "40")     # 底带里非绿像素少于此→样本不足,"看不清"
VISION_OCC_MIN_BOARD_FRAC = _f("ANIMA_VISION_OCC_MIN_BOARD_FRAC", "0.02")  # 绿板面积占画面比低于此→没找到板
VISION_OCC_RECT_CELL_PX = _i("ANIMA_VISION_OCC_RECT_CELL_PX", "48")   # 矫正(去斜视)后每格边长像素
# 板方向约定:探测到的板四角(图中 左上/右上/右下/左下)与棋盘格坐标的对应,按 90° 一档旋转(0-3)。
# 默认 0 = 相机从白方一侧看盘(图下缘=rank1、图左=a 列)。这是"一次性棋盘外参"级别的约定,换机位改它。
VISION_OCC_QUARTER_TURNS = _i("ANIMA_VISION_OCC_QUARTER_TURNS", "0")

# ---- 象棋引擎（ANIMA 自己的脑子）----
CHESS_DEPTH = _i("ANIMA_CHESS_DEPTH", "3")
CHESS_TIME = _f("ANIMA_CHESS_TIME", "1.5")


# ---- 路径派生（无绝对路径硬编码）----
def chess_engine_path() -> str:
    """ANIMA 复用的象棋引擎路径：默认从仓库结构派生（anima-zero 上溯到 career-projects 根，
    再拼 3-anima-chess-engine/chess/engine.py），可用 env ANIMA_CHESS_ENGINE_PATH 覆盖。"""
    env = os.getenv("ANIMA_CHESS_ENGINE_PATH")
    if env:
        return env
    # src/config.py → src → anima-zero → 1-vla-project-soma-chess → <career-projects 根>
    root = Path(__file__).resolve().parents[3]
    return str(root / "3-anima-chess-engine" / "chess" / "engine.py")


def discover_board_font() -> str | None:
    """发现式找一个可用的等宽/无衬线粗体 TTF（跨发行版/系统），找不到返回 None（调用方回退 PIL 默认）。
    可用 env ANIMA_BOARD_FONT 指定。两侧（渲染/视觉）在同一机器上会发现到同一字体。"""
    env = os.getenv("ANIMA_BOARD_FONT")
    if env and os.path.exists(env):
        return env
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",     # Debian/Ubuntu
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",              # Fedora/Arch
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",  # macOS
        "C:\\Windows\\Fonts\\arialbd.ttf",                          # Windows
        os.path.expanduser("~/.fonts/DejaVuSans-Bold.ttf"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None
