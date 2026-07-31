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
        60, validation_alias="ANIMA_MAX_STEPS", ge=1,
        description="ReAct 主循环单轮步数上限（一条用户消息内最多转几个「看→想→动」step）。"
                    "v0.9 起它是**安全带、不是节拍器**：一轮什么时候收尾由 LLM 自己出文字决定，"
                    "这个值只在它转不出来时兜底。口径=「一个回合做一件事」——下棋的一件事是一手棋"
                    "（实测 2-6 步，自然收尾、根本碰不到上限），导航的一件事是「找到厨房」"
                    "（几十步，要一路跑到收敛）。"
                    "【为什么 v0.8 的 8 被改掉】v0.8 定 8 是因为当时长回合有三个真病根：目标会滑出"
                    "上下文、跑起来不可中断、费用不可控。到 v0.9 三个分别有解了——核心任务寄存器"
                    "（v0.7 起）托住目标、网页有停止按钮、turn_time_budget_s 兜住费用，所以放开。"
                    "【但 v0.7 那个废案仍然是废案】当年调到 400 是拿单轮去跑「一句话下完整盘」的"
                    "跨回合循环（单会话 900+ 条流水、45-90 分钟不可中断不可审）——那是把多件事塞进"
                    "一个回合，与本值大小无关，**不要再那样用**。")
    turn_time_budget_s: float = Field(
        900, validation_alias="ANIMA_TURN_TIME_BUDGET_S", gt=0,
        description="单轮墙钟上限（秒），默认 900=15 分钟。步数管不住「每步很慢」的世界"
                    "（物理世界做一个动作就要几秒），墙钟才是真正的费用闸。到顶=走 overflow 礼貌停顿"
                    "（可续），不是报错。")
    context_token_budget: int = Field(
        6000, validation_alias="ANIMA_CONTEXT_BUDGET", ge=100,
        description="上下文滑窗 token 预算（粗估 3 字符≈1 token）：从最近往前装历史，超预算即截断。")

    # ---- 笔记寄存器（v1.0：LLM 自管的第二个状态通道）----
    notes_max: int = Field(
        20, validation_alias="ANIMA_NOTES_MAX", ge=1,
        description="笔记本最多存几条。核心任务管「我在干什么」（一句话），笔记管「我发现了什么」"
                    "（一条条追加）——两者都常驻注入系统提示、不随对话变长滑走。"
                    "记满了**不静默丢弃**：加不进去时明确告诉 LLM，让它自己划掉没用的再记。")
    note_max_chars: int = Field(
        120, validation_alias="ANIMA_NOTE_MAX_CHARS", ge=10,
        description="单条笔记的字数上限。笔记是备忘不是日记；超长就退回让它自己缩写，"
                    "**绝不截断**（截断会把一条笔记变成半句话，比没有更糟）。")

    # ---- 世界给的文本：进大脑之前的长度上限（安全，见 core/trust.py）----
    # 世界的说明书和工具描述都是**远端写的文本**，会进系统提示词和工具单。除了信任审批那道闸，
    # 还要有个长度上限：一份 500KB 的说明书不需要任何巧思就能把上下文预算撑爆、把每一轮都变贵。
    # 上限之外的部分**如实截断并说明**（不静默丢——静默丢会让人以为世界写的东西全生效了）。
    world_guidance_max_chars: int = Field(
        4000, validation_alias="ANIMA_WORLD_GUIDANCE_MAX_CHARS", ge=100,
        description="世界说明书注入系统提示的字数上限。真实世界的说明书都在一千字上下"
                    "（sim-house-nav 约 844 字），4000 是宽裕的；它挡的是恶意或失控的超长文本。")
    world_tool_desc_max_chars: int = Field(
        1000, validation_alias="ANIMA_WORLD_TOOL_DESC_MAX_CHARS", ge=50,
        description="单个工具描述进工具单的字数上限。工具描述是 3~4 句话说清「何时调/何时别调」，"
                    "1000 字已经远超正常；同样只挡异常，不影响正经世界。")

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
    model_demo: str = Field(
        "qwen3:4b-instruct-2507", validation_alias="ANIMA_DEMO_MODEL",
        description="`anima demo` 的本地演示脑（经 Ollama，纯 CPU 可跑）。选型：4B 是最小且"
                    "真正可靠的工具调用尺寸（BFCL 函数调用榜有正式条目；1.7B/0.6B 不可靠），"
                    "Apache-2.0，Q4 约 2.5GB。它是纯文本模型——演示世界的传感器全是文字"
                    "（look 工具 + state 读数），不需要视觉。")


# 启动即校验：env/.env 有非法值这里直接抛可读的 ValidationError（fail-fast）。
_settings = Settings()

# ---- 兼容层：大写常量原名 re-export（消费方 `config.MAX_STEPS` 等零改动）----
MAX_STEPS = _settings.max_steps
TURN_TIME_BUDGET_S = _settings.turn_time_budget_s
CONTEXT_TOKEN_BUDGET = _settings.context_token_budget
NOTES_MAX = _settings.notes_max
NOTE_MAX_CHARS = _settings.note_max_chars
WORLD_GUIDANCE_MAX_CHARS = _settings.world_guidance_max_chars
WORLD_TOOL_DESC_MAX_CHARS = _settings.world_tool_desc_max_chars
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
MODEL_DEMO = _settings.model_demo


# ---- 给网页显示的「核心运行参数」----
# 收录判据：**决定一个回合能跑多深、多久、记得多少**的三个闸——它们直接决定用户看到的行为，
# 所以值得常驻在界面上。其余（各类超时、模型 id）属于运维细节，不占界面。
# ⛔ 名字/值/env 名/说明四样全部从下面 Settings 的字段定义现读，前端一个都不许自己写死。
_RUNTIME_PARAMS_SHOWN = ("max_steps", "turn_time_budget_s", "context_token_budget",
                         "notes_max")
# One-line labels for display. The Settings `description` is a whole paragraph and does not
# fit in the panel, so these are the short forms. English, matching the rest of the interface
# — the frontend renders them as sent.
# 显示用的一行短名（Settings 的 description 是整段说明，界面上放不下）。用英文，与界面其余部分一致
# ——前端是原样渲染它们的。
_RUNTIME_PARAM_LABELS = {
    "max_steps": "Steps per turn",
    "turn_time_budget_s": "Time per turn (s)",
    "context_token_budget": "Context budget (tokens)",
    "notes_max": "Notebook capacity",
}

# What the panel shows as the hint for each parameter.
#
# ⛔ Deliberately NOT the field's `description`. Those descriptions are long, and they are the
# maintainer's reasoning about why a value is what it is — internal documentation, in Chinese
# by the project's own language rule. Sending them to the interface put a paragraph of
# internal Chinese rationale into an English UI. One sentence of English here, the reasoning
# left where it belongs.
#
# ⛔ 这里**有意不用**字段的 `description`。那些描述很长，写的是维护者"为什么定这个值"的思考
#    ——按本项目自己的语言规则，那是内部文档、保持中文。把它们送到界面上，等于把一整段中文的
#    内部理由塞进一个英文界面。这里给一句英文，理由留在它该在的地方。
_RUNTIME_PARAM_HINTS = {
    "max_steps": ("A seatbelt, not a metronome. The model decides when a turn ends by "
                  "producing prose; this only catches it going in circles."),
    "turn_time_budget_s": ("Wall clock per turn. A step count cannot restrain a world where "
                           "each step is slow, so this is the real cost gate. Reaching it is "
                           "a pause you can continue from, not an error."),
    "context_token_budget": ("Sliding-window budget for history, packed from the most recent "
                             "backwards and truncated at the limit."),
    "notes_max": ("How many notes the notebook holds. When it is full the model is told so "
                  "and can strike an entry — nothing is discarded silently."),
}


def runtime_params() -> list[dict]:
    """核心运行参数的当前生效值 + 它们的 env 名与说明（给 GET /api/config，网页只做显示器）。"""
    out: list[dict] = []
    for name in _RUNTIME_PARAMS_SHOWN:
        field = Settings.model_fields[name]
        alias = field.validation_alias
        out.append({
            "key": name,
            "label": _RUNTIME_PARAM_LABELS.get(name, name),
            "value": getattr(_settings, name),
            "env": alias if isinstance(alias, str) else name.upper(),
            "description": _RUNTIME_PARAM_HINTS.get(name, ""),
        })
    return out


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
#    (2026-06-28 教训：加 sim-chess 时只写了它,把当时的 sim-desk 世界挤没了；
#     那个世界已在 v1.1.1 删除,但这条教训是这条规矩存在的唯一证据,留着)。
def worlds() -> list[tuple[str, str]]:
    """可连的世界清单 [(name, url)]。env ANIMA_WORLDS="name=url,name2=url2" 覆盖；没设=全部已知世界。
    在【调用时】读 env（不在 import 时）——调用方通常先 load_dotenv，.env 里的地址才生效。"""
    raw = os.getenv("ANIMA_WORLDS", "").strip()
    if raw:
        return _pairs(raw)

    # 仓内那几个世界**只有在那个目录真的存在时**才列出来。
    #
    # ⚠️ 这不是"替换全集"（T0 红线）：一个 checkout 里 world/ 全在，所以列出来的和以前一模一样。
    # 变的只是**用 pip 装的人**——他没有仓库，那几个地址对他而言是必然连不上的条目，
    # 装完第一眼就像坏的。世界在不在，按"它的目录在不在"判断，比按"代码里写死了几个"判断更接近事实。
    #
    # ⚠️ v1.1.1 起 wheel 里不再带任何世界，所以**用 pip 装的人拿到的是一张空清单**——这是
    # 有意的，不是 bug。世界是独立的程序：clone 本仓能拿到 world/ 下的几个，或者照
    # docs/awi-spec-v1.md 自己写一个，再用 `anima world add` 注册。
    #
    # ⚠️ Not a replacement of the whole set: in a checkout every world/ directory is there,
    # so the list comes out exactly as before. What changes is the person who installed with
    # pip — they have no repository, and those addresses are entries that can never connect.
    # Since v1.1.1 the wheel carries no world at all, so a pip install yields an **empty**
    # list. That is deliberate: a world is a separate program, obtained by cloning this
    # repository or by writing one against docs/awi-spec-v1.md.
    out: list[tuple[str, str]] = []
    repo_worlds = [
        ("sim-chess", "SIM_CHESS_URL", "http://localhost:8102"),
        ("camera", "CAMERA_URL", "http://localhost:8104"),
        ("sim-house-nav", "SIM_HOUSE_NAV_URL", "http://localhost:8112"),
    ]
    world_dir = os.path.join(paths.REPO_ROOT, "world")
    if os.path.isdir(world_dir):
        out += [(name, _s(env, default)) for name, env, default in repo_worlds]
    # gazebo-chess 不在默认清单里：它的代码住在伴随仓 open-chess-robot（2026-07-08 迁出），
    # 默认列出它对绝大多数人就是一个永远 offline 的死条目（v1.2 清障）。
    # 但老能力不丢（T0）：显式设了 GAZEBO_CHESS_URL 的人，照旧出现在清单里。
    gazebo = os.getenv("GAZEBO_CHESS_URL", "").strip()
    if gazebo:
        out.append(("gazebo-chess", gazebo))
    return out


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
