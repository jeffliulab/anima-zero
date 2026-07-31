"""选脑工厂:大脑名字 → 具体大脑实现。

全部大脑都登记在下面 `_registry()` 这一张表里(单一真相)。每个大脑写清四样:显示名、版本号、
是云端还是本地、怎么创建。**版本号只在这张表里写**——以后想给某个大脑换版本,改这里对应那一行即可。

  在线(需要 API key):opus / haiku(ANTHROPIC_API_KEY)、gpt-5.5 / gpt-5.4 / gpt-5.4-mini(OPENAI_API_KEY)
  本地(经 Ollama,免费):qwen3-vl(OLLAMA_BASE_URL + ANIMA_QWEN3VL_MODEL 版本号)

所有环境变量都在调用时读取(而非 import 时),这样 .env 先加载、再选脑也生效。
怎么再加一个大脑,见同目录的 README.md(《如何给 ANIMA 增加一个语言大脑》)。
"""
from __future__ import annotations

import json
import os
import urllib.request

from .. import config
from .base import LLM
from .claude import ClaudeLLM
from .mock import MockLLM
from .openai_compat import OpenAICompatLLM

# 默认大脑 / Ollama 探活超时 → 中央 config（env 可覆盖）。
DEFAULT_BRAIN = config.DEFAULT_BRAIN
OLLAMA_PROBE_TIMEOUT = config.OLLAMA_PROBE_TIMEOUT


def _ollama_tags(base_url: str) -> set[str]:
    """查 Ollama 已拉取的模型 tag(走 OpenAI 兼容口 /models);连不上就当没有。"""
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/models", timeout=OLLAMA_PROBE_TIMEOUT) as r:
            data = json.load(r)
        return {m.get("id", "") for m in data.get("data", [])}
    except Exception:
        return set()


def _registry() -> dict[str, dict]:
    """全部大脑的单一登记表。每项:
        label  显示名      model  版本号(调 API 用的字符串)
        hosting  api / local  build() 创建大脑   ready() 是否配置好(有 key / 模型已 pull)
    要加新大脑,往这张表里加一项即可(详见同目录 README.md)。
    """
    okey = os.getenv("OPENAI_API_KEY", "")
    ollama = config.OLLAMA_BASE_URL
    # 模型 id 全部来自中央 config（单一来源，每个 env 可覆盖）
    qwen_model = config.MODEL_QWEN
    opus_model, haiku_model = config.MODEL_OPUS, config.MODEL_HAIKU
    gpt55_model, gpt54_model, gpt54_mini_model = config.MODEL_GPT_55, config.MODEL_GPT_54, config.MODEL_GPT_54_MINI
    demo_model = config.MODEL_DEMO
    has_anthropic = bool(os.getenv("ANTHROPIC_API_KEY"))
    has_openai = bool(okey)
    tags: set[str] | None = None  # 本地脑可用性才需查 Ollama,惰性求值

    def ollama_ready(model: str) -> bool:
        nonlocal tags
        if tags is None:
            tags = _ollama_tags(ollama)
        return model in tags

    return {
        # —— 在线大脑(key 在各自的类里读环境变量)——
        "opus": {"vendor": "Anthropic", "label": "Claude Opus 4.8", "model": opus_model, "hosting": "api",
                 "build": lambda: ClaudeLLM(opus_model),
                 "ready": lambda: has_anthropic},
        "haiku": {"vendor": "Anthropic", "label": "Claude Haiku 4.5", "model": haiku_model, "hosting": "api",
                  "build": lambda: ClaudeLLM(haiku_model),
                  "ready": lambda: has_anthropic},
        "gpt-5.5": {"vendor": "OpenAI", "label": "GPT-5.5", "model": gpt55_model, "hosting": "api",
                    "build": lambda: OpenAICompatLLM(gpt55_model, None, okey),
                    "ready": lambda: has_openai},
        "gpt-5.4": {"vendor": "OpenAI", "label": "GPT-5.4", "model": gpt54_model, "hosting": "api",
                    "build": lambda: OpenAICompatLLM(gpt54_model, None, okey),
                    "ready": lambda: has_openai},
        "gpt-5.4-mini": {"vendor": "OpenAI", "label": "GPT-5.4-mini", "model": gpt54_mini_model, "hosting": "api",
                         "build": lambda: OpenAICompatLLM(gpt54_mini_model, None, okey),
                         "ready": lambda: has_openai},
        # —— 本地大脑(经 Ollama,免费离线;版本号可在 .env 改)——
        "qwen3-vl": {"vendor": "Ollama · local", "label": "Qwen3-VL 8B", "model": qwen_model, "hosting": "local",
                     "build": lambda: OpenAICompatLLM(qwen_model, ollama, "ollama"),
                     "ready": lambda: ollama_ready(qwen_model)},
        # demo 演示脑：纯文本（vision=False），纯 CPU 可跑。它的世界传感器全是文字，
        # 不需要眼睛；选型理由写在 config 的 model_demo 字段说明里。
        "demo": {"vendor": "Ollama · local", "label": "Qwen3 4B Instruct (demo brain, CPU)", "model": demo_model,
                 "hosting": "local",
                 "build": lambda: OpenAICompatLLM(demo_model, ollama, "ollama", vision=False),
                 "ready": lambda: ollama_ready(demo_model)},
        # —— 不需要 key 的演示脑：它**不思考**，只把链路走一遍（见 llm/mock.py）——
        # 列在最后、标签里直说它不思考：它是给"刚装完想看看能不能跑"用的，不是一个可选的大脑。
        # ready 恒真是它唯一的意义所在——没有 key 的人也得有一个能跑的东西。
        "mock": {"vendor": "built in · no key needed", "label": "Mock (does not think — demonstrates the chain)", "model": "mock",
                 "hosting": "local", "build": MockLLM, "ready": lambda: True},
    }


def list_brains() -> list[dict]:
    """全部大脑清单:名字 + 厂商 + 显示名 + 版本号 + 类型 + 是否配置好(给前端选择器 / 连通自检用)。"""
    return [
        {"name": name, "vendor": spec["vendor"], "label": spec["label"], "model": spec["model"],
         "hosting": spec["hosting"], "available": spec["ready"]()}
        for name, spec in _registry().items()
    ]


def make_llm(name: str | None = None) -> LLM:
    name = name or DEFAULT_BRAIN
    reg = _registry()
    if name not in reg:
        raise KeyError(f"Unknown brain: {name}. Available: {', '.join(reg)}")
    return reg[name]["build"]()
