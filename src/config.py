"""中央配置（脑侧）—— 所有可调数字 / 默认值 / 模型 id / 路径派生 的**单一来源**。

⛔ 禁止硬编码：凡是可调的数字、默认、模型 id、路径，都集中在这里，且**全部 env 可覆盖**；
代码各处从这里读，不再 inline 写死。域常量（棋盘 8×8、FEN 符号、枚举）不在此（那是定义）。

"""
from __future__ import annotations

import os


def _i(key: str, default: str) -> int:
    return int(os.getenv(key, default))


def _f(key: str, default: str) -> float:
    return float(os.getenv(key, default))


def _s(key: str, default: str) -> str:
    return os.getenv(key, default)


# ---- 编排器 / 上下文 ----
MAX_STEPS = _i("ANIMA_MAX_STEPS", "8")                   # ReAct 主循环最多转几轮
CONTEXT_TOKEN_BUDGET = _i("ANIMA_CONTEXT_BUDGET", "6000")  # 上下文滑窗 token 预算

# ---- 开发自测接口（仅开发用，默认关）----
# 开着时后端暴露 POST /api/dev/turn：一次调用跑完整一轮对话并返回该轮的全部 Session Logs 流水，
# 供开发者/agent 自测断言 llm_call→service_call→world_call 链。生产/演示环境保持默认关闭。
DEV_API = os.getenv("ANIMA_DEV_API", "0") not in ("0", "false", "False")

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
SERVICE_MCP_TIMEOUT = _f("ANIMA_SERVICE_MCP_TIMEOUT", "15")          # 挂载服务一次问答的死线（顾问=纯计算，秒回）
TITLE_MAX_LEN = _i("ANIMA_TITLE_MAX_LEN", "24")
AWI_LOG_MAXLEN = _i("ANIMA_AWI_LOG_MAXLEN", "400")
AWI_POLL_INTERVAL_S = _f("ANIMA_AWI_POLL_INTERVAL_S", "0.25")

# ---- 日志留痕（session_log）----
# 留痕文本的最大留存长度（字符）——只是给写盘一个上界防失控，正常条目都远短于此 = 等同"留全文"。
LOG_MAX_SYSTEM = _i("ANIMA_LOG_MAX_SYSTEM", "8000")
LOG_MAX_USER = _i("ANIMA_LOG_MAX_USER", "8000")
LOG_MAX_REPLY = _i("ANIMA_LOG_MAX_REPLY", "20000")

# ---- LLM ----
MAX_TOKENS = _i("ANIMA_MAX_TOKENS", "1024")
OLLAMA_PROBE_TIMEOUT = _f("ANIMA_OLLAMA_PROBE_TIMEOUT", "0.6")
OLLAMA_BASE_URL = _s("OLLAMA_BASE_URL", "http://localhost:11434/v1")
DEFAULT_BRAIN = _s("ANIMA_DEFAULT_BRAIN", "gpt-5.4")
# 模型 id 单一来源（每个可 env 覆盖）
MODEL_OPUS = _s("ANIMA_CLAUDE_OPUS_MODEL", "claude-opus-4-8")
MODEL_HAIKU = _s("ANIMA_CLAUDE_HAIKU_MODEL", "claude-haiku-4-5")
MODEL_GPT_55 = _s("ANIMA_OPENAI_GPT55_MODEL", "gpt-5.5")
MODEL_GPT_54 = _s("ANIMA_OPENAI_GPT54_MODEL", "gpt-5.4")
MODEL_GPT_54_MINI = _s("ANIMA_OPENAI_GPT54_MINI_MODEL", "gpt-5.4-mini")
MODEL_QWEN = _s("ANIMA_QWEN3VL_MODEL", "qwen3-vl:8b")

def _pairs(raw: str) -> list[tuple[str, str]]:
    """解析 "name=url,name2=url2" 清单（worlds/services 共用）。"""
    pairs: list[tuple[str, str]] = []
    for item in raw.split(","):
        item = item.strip()
        if "=" not in item:
            continue
        name, url = (s.strip() for s in item.split("=", 1))
        if name and url:
            pairs.append((name, url))
    return pairs


# ---- 世界清单（单一来源：后端 server 与 dev_turn CLI 都从这里读）----
# ⛔ T0：默认清单必须含所有已知世界——加世界=往这份默认里【追加】,绝不替换
#    (2026-06-28 教训：加 sim-chess 时只写了它,把 sim-desk 挤没了)。
def worlds() -> list[tuple[str, str]]:
    """可连的世界清单 [(name, url)]。env ANIMA_WORLDS="name=url,name2=url2" 覆盖；没设=全部已知世界。
    在【调用时】读 env（不在 import 时）——调用方通常先 load_dotenv，.env 里的地址才生效。"""
    raw = os.getenv("ANIMA_WORLDS", "").strip()
    if not raw:
        # 各世界默认地址(env 可覆盖)：sim-desk :8100、sim-chess :8102、camera :8104、gazebo-chess :8106
        return [
            ("sim-desk", _s("SIM_DESK_URL", "http://localhost:8100")),
            ("sim-chess", _s("SIM_CHESS_URL", "http://localhost:8102")),
            ("camera", _s("CAMERA_URL", "http://localhost:8104")),
            ("gazebo-chess", _s("GAZEBO_CHESS_URL", "http://localhost:8106")),
        ]
    return _pairs(raw)


# ---- 挂载服务清单（与 worlds() 完全对称；Host 组装 = 标准 MCP：连哪些 server 由大脑自己决定）----
# service=顾问（纯计算、无画面、无副作用），是大脑的能力、不属于任何世界——world 不声明服务。
# ⛔ T0：加服务=往这份默认里【追加】,绝不替换。
def services() -> list[tuple[str, str]]:
    """挂载服务清单 [(name, url)]。env ANIMA_SERVICES="name=url,..." 覆盖；没设=全部已知服务。
    在【调用时】读 env（同 worlds()）。"""
    raw = os.getenv("ANIMA_SERVICES", "").strip()
    if not raw:
        return [
            ("boardgame-engine", _s("ANIMA_BOARDGAME_ENGINE_URL", "http://localhost:8108")),
        ]
    return _pairs(raw)

# （v0.5 重构起：对弈行为树 / 视觉 / 脑侧引擎的全部配置已随 game mode 删除——
#   引擎可调项住引擎 service 自带 env（services/boardgame_engine/app.py），世界可调项住各世界自带 env。）
