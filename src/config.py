"""中央配置（脑侧）—— 所有可调数字 / 默认值 / 模型 id 的**单一来源**（配置体系说明书）。

体系（v0.8 起采用 pydantic-settings，Python/FastAPI 生态标准做法）：
- **默认值住这里**：每个可调项是 `Settings` 的一个字段，`Field(default=…, description=…)`——
  说明随代码走、启动即类型校验（fail-fast：env 填了非法值当场报可读错误，不再等运行时炸）。
- **env 覆盖**：每个字段经 `validation_alias` 绑定环境变量名（与历史完全一致，如
  `ANIMA_MAX_STEPS`），优先级 = **shell env > .env 文件 > 代码默认**（pydantic 标准）。
- **.env**：由 Settings 直接读仓库根 `.env`（`paths.ENV_FILE`）——v0.8 起 .env 对**全部**
  字段生效（旧版标量在 import 时求值、早于 load_dotenv，.env 对标量其实不生效，是个缺口）。
- **消费方接口不变**：文件尾把全部大写常量原名 re-export（`config.MAX_STEPS` 照旧可用）。
- **worlds() / services()**：保持函数、在【调用时】读 env（不随 Settings 在 import 时定死）——
  后端/CLI 先 load_dotenv 再调用的既有语义不变。
- ⛔ 禁止硬编码：凡可调的数字/默认/模型 id 都集中在此;域常量（棋盘 8×8、FEN 符号、枚举）
  不在此（那是定义，不是配置）。
"""
from __future__ import annotations

import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from . import paths


class Settings(BaseSettings):
    """脑侧全部可调项。字段名小写；env 名走 validation_alias（与历史 env 名逐一相同）。"""

    model_config = SettingsConfigDict(
        env_file=paths.ENV_FILE,      # 仓库根 .env（不存在则跳过）
        env_file_encoding="utf-8",
        extra="ignore",               # .env 里的世界侧/引擎侧变量（GZCHESS_* 等）不属于脑侧，忽略
    )

    # ---- 编排器 / 上下文 ----
    max_steps: int = Field(
        8, validation_alias="ANIMA_MAX_STEPS", ge=1,
        description="ReAct 主循环单轮步数上限（一条用户消息内最多转几个「看→想→动」step）。"
                    "回合制铁律：每手/每步停下等用户——一手棋实测 2-6 步，8 留足余量。"
                    "历史教训：v0.7 对局 1-3 曾调到 400 跑「一句话下完整盘」的循环模式，已否定废弃"
                    "（目标滑出上下文、中途停摆、单会话 900+ 条流水失控）；未来若真要长循环，"
                    "必须显式设计新模式，禁止靠调大本值复活（见 v0.8 审计）。")
    context_token_budget: int = Field(
        6000, validation_alias="ANIMA_CONTEXT_BUDGET", ge=100,
        description="上下文滑窗 token 预算（粗估 3 字符≈1 token）：从最近往前装历史，超预算即截断。")

    # ---- 开发自测接口（仅开发用，默认关）----
    dev_api: bool = Field(
        False, validation_alias="ANIMA_DEV_API",
        description="开着时后端暴露 POST /api/dev/turn：一次调用跑完整一轮并返回该轮 Session Logs "
                    "流水，供自测断言 llm_call→service_call→world_call 链。生产/演示保持关闭。")

    # ---- 世界客户端：快速读操作的死线（读操作本该秒回，死线语义正确）----
    world_timeout: float = Field(
        30, validation_alias="ANIMA_WORLD_TIMEOUT", gt=0,
        description="capabilities 握手 / perceive 等【快速读操作】的超时秒数。")
    world_probe_timeout: float = Field(
        1.5, validation_alias="ANIMA_WORLD_PROBE_TIMEOUT", gt=0,
        description="在线探活（/health，不记流量）的超时秒数。")
    world_status_timeout: float = Field(
        5, validation_alias="ANIMA_WORLD_STATUS_TIMEOUT", gt=0,
        description="世界本地 /status（人类调试台真值）的超时：有的世界现算真值"
                    "（如 gazebo 抓一段位姿）比 /health 慢，给宽一点。")

    # ---- 动作(invoke)的「生命迹象」语义（v0.5 wave0 框架修正）----
    # 物理动作可能要几十秒：不对「动作比 X 秒长」判死，而对「X 秒没有任何生命迹象」判失联——
    # 世界经 MCP progress 报进度即续命（run_alive 落地），另设总上限硬闸。
    world_connect_timeout: float = Field(
        5, validation_alias="ANIMA_WORLD_CONNECT_TIMEOUT", gt=0,
        description="连上世界 / MCP 握手的死线（秒）。")
    world_liveness_timeout: float = Field(
        20, validation_alias="ANIMA_WORLD_LIVENESS_TIMEOUT", gt=0,
        description="无生命迹象判失联的窗口（秒）；世界报一次 progress 即续命。")
    world_invoke_hard_cap: float = Field(
        180, validation_alias="ANIMA_WORLD_INVOKE_HARD_CAP", gt=0,
        description="单次动作总上限（秒）——有进度也不无限等的硬闸。")
    bridge_watchdog_poll_s: float = Field(
        0.25, validation_alias="ANIMA_BRIDGE_WATCHDOG_POLL_S", gt=0,
        description="监督器巡检步长（秒），也是取消响应的粒度。")
    bridge_grace_s: float = Field(
        5, validation_alias="ANIMA_BRIDGE_GRACE_S", ge=0,
        description="外层后备宽限（秒）——监督器才是权威，这只是安全带。")
    service_mcp_timeout: float = Field(
        15, validation_alias="ANIMA_SERVICE_MCP_TIMEOUT", gt=0,
        description="挂载服务一次问答的死线（秒）——顾问=纯计算，理应秒回。")

    # ---- 会话 / AWI 日志 ----
    title_max_len: int = Field(
        24, validation_alias="ANIMA_TITLE_MAX_LEN", ge=1,
        description="会话标题取用户首句的前几个字。")
    awi_log_maxlen: int = Field(
        400, validation_alias="ANIMA_AWI_LOG_MAXLEN", ge=1,
        description="脑端内存里保留多少条 AWI 流量历史（/awi 仪表盘用；前端显示数须 ≤ 此值）。")
    awi_poll_interval_s: float = Field(
        0.25, validation_alias="ANIMA_AWI_POLL_INTERVAL_S", gt=0,
        description="/awi 仪表盘流量轮询间隔（秒）。")

    # ---- 日志留痕（session_log）：写盘上界防失控，正常条目远短于此=等同留全文 ----
    log_max_system: int = Field(
        8000, validation_alias="ANIMA_LOG_MAX_SYSTEM", ge=1,
        description="llm_call 留痕里 system 提示的最大留存字符数。")
    log_max_user: int = Field(
        8000, validation_alias="ANIMA_LOG_MAX_USER", ge=1,
        description="llm_call 留痕里最近一条用户消息的最大留存字符数。")
    log_max_reply: int = Field(
        20000, validation_alias="ANIMA_LOG_MAX_REPLY", ge=1,
        description="llm_call 留痕里模型回复的最大留存字符数。")

    # ---- LLM ----
    max_tokens: int = Field(
        1024, validation_alias="ANIMA_MAX_TOKENS", ge=1,
        description="单次 LLM 调用的输出 token 上限。")
    ollama_probe_timeout: float = Field(
        0.6, validation_alias="ANIMA_OLLAMA_PROBE_TIMEOUT", gt=0,
        description="探测本地 Ollama 是否在线的超时（秒）。")
    ollama_base_url: str = Field(
        "http://localhost:11434/v1", validation_alias="OLLAMA_BASE_URL",
        description="本地 Ollama 的 OpenAI 兼容端点。")
    default_brain: str = Field(
        "gpt-5.4", validation_alias="ANIMA_DEFAULT_BRAIN",
        description="默认选用的大脑名（llm/factory.py 登记表里的名字）。")
    # 模型 id 单一来源（每个可 env 覆盖）
    model_opus: str = Field("claude-opus-4-8", validation_alias="ANIMA_CLAUDE_OPUS_MODEL",
                            description="Claude Opus 的模型 id。")
    model_haiku: str = Field("claude-haiku-4-5", validation_alias="ANIMA_CLAUDE_HAIKU_MODEL",
                             description="Claude Haiku 的模型 id。")
    model_gpt_55: str = Field("gpt-5.5", validation_alias="ANIMA_OPENAI_GPT55_MODEL",
                              description="GPT-5.5 的模型 id。")
    model_gpt_54: str = Field("gpt-5.4", validation_alias="ANIMA_OPENAI_GPT54_MODEL",
                              description="GPT-5.4 的模型 id。")
    model_gpt_54_mini: str = Field("gpt-5.4-mini", validation_alias="ANIMA_OPENAI_GPT54_MINI_MODEL",
                                   description="GPT-5.4-mini 的模型 id。")
    model_qwen: str = Field("qwen3-vl:8b", validation_alias="ANIMA_QWEN3VL_MODEL",
                            description="本地 Qwen3-VL（Ollama）的模型名。")


# 启动即校验：env/.env 有非法值这里直接抛可读的 ValidationError（fail-fast）。
_settings = Settings()

# ---- 兼容层：大写常量原名 re-export（消费方 `config.MAX_STEPS` 等零改动）----
MAX_STEPS = _settings.max_steps
CONTEXT_TOKEN_BUDGET = _settings.context_token_budget
DEV_API = _settings.dev_api
WORLD_TIMEOUT = _settings.world_timeout
WORLD_PROBE_TIMEOUT = _settings.world_probe_timeout
WORLD_STATUS_TIMEOUT = _settings.world_status_timeout
WORLD_CONNECT_TIMEOUT = _settings.world_connect_timeout
WORLD_LIVENESS_TIMEOUT = _settings.world_liveness_timeout
WORLD_INVOKE_HARD_CAP = _settings.world_invoke_hard_cap
BRIDGE_WATCHDOG_POLL_S = _settings.bridge_watchdog_poll_s
BRIDGE_GRACE_S = _settings.bridge_grace_s
SERVICE_MCP_TIMEOUT = _settings.service_mcp_timeout
TITLE_MAX_LEN = _settings.title_max_len
AWI_LOG_MAXLEN = _settings.awi_log_maxlen
AWI_POLL_INTERVAL_S = _settings.awi_poll_interval_s
LOG_MAX_SYSTEM = _settings.log_max_system
LOG_MAX_USER = _settings.log_max_user
LOG_MAX_REPLY = _settings.log_max_reply
MAX_TOKENS = _settings.max_tokens
OLLAMA_PROBE_TIMEOUT = _settings.ollama_probe_timeout
OLLAMA_BASE_URL = _settings.ollama_base_url
DEFAULT_BRAIN = _settings.default_brain
MODEL_OPUS = _settings.model_opus
MODEL_HAIKU = _settings.model_haiku
MODEL_GPT_55 = _settings.model_gpt_55
MODEL_GPT_54 = _settings.model_gpt_54
MODEL_GPT_54_MINI = _settings.model_gpt_54_mini
MODEL_QWEN = _settings.model_qwen


def _s(key: str, default: str) -> str:
    """worlds()/services() 专用的调用时 env 读取（这两个清单不随 Settings 在 import 时定死）。"""
    return os.getenv(key, default)


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
        # 各世界默认地址(env 可覆盖)：sim-desk :8100、sim-chess :8102、camera :8104、
        #                              gazebo-chess :8106、sim-house-nav :8112
        return [
            ("sim-desk", _s("SIM_DESK_URL", "http://localhost:8100")),
            ("sim-chess", _s("SIM_CHESS_URL", "http://localhost:8102")),
            ("camera", _s("CAMERA_URL", "http://localhost:8104")),
            ("gazebo-chess", _s("GAZEBO_CHESS_URL", "http://localhost:8106")),
            ("sim-house-nav", _s("SIM_HOUSE_NAV_URL", "http://localhost:8112")),
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
