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
WORLD_TIMEOUT = _f("ANIMA_WORLD_TIMEOUT", "30")
WORLD_PROBE_TIMEOUT = _f("ANIMA_WORLD_PROBE_TIMEOUT", "1.5")
# 世界本地 /status(人类调试台真值)的超时:有的世界现算真值(如 gazebo-chess 抓一段 gz 位姿)比 /health 慢,给它宽一点。
WORLD_STATUS_TIMEOUT = _f("ANIMA_WORLD_STATUS_TIMEOUT", "5")
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
GAME_WORLD_TIMEOUT = _f("ANIMA_GAME_WORLD_TIMEOUT", "2.5")  # 对弈专用世界 client 短超时(协作式取消够快的关键)
GAME_CANCEL_JOIN_S = _f("ANIMA_GAME_CANCEL_JOIN_S", "3.0")  # manager 停旧 runner 的 join 上限
GAME_RESIGN_EVAL = _i("ANIMA_GAME_RESIGN_EVAL", "-900")    # 我方视角形势评分(厘兵)低于此→倾向认输(约落后一个皇后)
GAME_RESIGN_CONFIRM = _i("ANIMA_GAME_RESIGN_CONFIRM", "3")  # 评分须连续这么多拍都极差才认输(避免兑子瞬间误判)
# 视觉(置信度/多帧确认)
VISION_AMBIGUITY_RATIO = _f("ANIMA_VISION_AMBIGUITY_RATIO", "0.7")  # Lowe 比值:最近/次近 SAD 超此→该格"看不清"
VISION_CONFIRM_FRAMES = _i("ANIMA_VISION_CONFIRM_FRAMES", "2")      # 多帧确认:候选局面连续几帧一致才采信

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
