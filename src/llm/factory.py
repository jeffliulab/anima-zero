"""选脑工厂:大脑名字 → 具体大脑实现。

五个大脑都登记在下面 `_registry()` 这一张表里(单一真相)。每个大脑写清四样:显示名、版本号、
是云端还是本地、怎么创建。**版本号只在这张表里写**——以后想给某个大脑换版本,改这里对应那一行即可。

  在线(需要 API key):opus / haiku(ANTHROPIC_API_KEY)、gpt-5.5 / gpt-4.1-nano(OPENAI_API_KEY)
  本地(经 Ollama,免费):qwen3-vl(OLLAMA_BASE_URL + ANIMA_QWEN3VL_MODEL 版本号)

所有环境变量都在调用时读取(而非 import 时),这样 .env 先加载、再选脑也生效。
怎么再加一个大脑,见同目录的 README.md(《如何给 ANIMA 增加一个语言大脑》)。
"""
from __future__ import annotations

import json
import os
import urllib.request

from .base import LLM
from .claude import ClaudeLLM
from .openai_compat import OpenAICompatLLM

# 没指定大脑时用哪个(可用 ANIMA_DEFAULT_BRAIN 覆盖);单一来源,presentation/server.py 也引用它。
DEFAULT_BRAIN = os.getenv("ANIMA_DEFAULT_BRAIN", "gpt-4.1-nano")
# 探测本地 Ollama 是否在线的超时(秒):要短(别拖慢前端选择器),又别太短误判慢启动 / 远程 Ollama。
OLLAMA_PROBE_TIMEOUT = 0.6


def _ollama_tags(base_url: str) -> set[str]:
    """查 Ollama 已拉取的模型 tag(走 OpenAI 兼容口 /models);连不上就当没有。"""
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/models", timeout=OLLAMA_PROBE_TIMEOUT) as r:
            data = json.load(r)
        return {m.get("id", "") for m in data.get("data", [])}
    except Exception:
        return set()


def _registry() -> dict[str, dict]:
    """五个大脑的单一登记表。每项:
        label  显示名      model  版本号(调 API 用的字符串)
        kind   api / local  build() 创建大脑   ready() 是否配置好(有 key / 模型已 pull)
    要加新大脑,往这张表里加一项即可(详见同目录 README.md)。
    """
    okey = os.getenv("OPENAI_API_KEY", "")
    ollama = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    qwen_model = os.getenv("ANIMA_QWEN3VL_MODEL", "qwen3-vl:8b")
    opus_model, haiku_model = "claude-opus-4-8", "claude-haiku-4-5"  # 版本号各写一处,显示名和 build 共用
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
        "opus": {"vendor": "Anthropic", "label": "Claude Opus 4.8", "model": opus_model, "kind": "api",
                 "build": lambda: ClaudeLLM(opus_model),
                 "ready": lambda: has_anthropic},
        "haiku": {"vendor": "Anthropic", "label": "Claude Haiku 4.5", "model": haiku_model, "kind": "api",
                  "build": lambda: ClaudeLLM(haiku_model),
                  "ready": lambda: has_anthropic},
        "gpt-5.5": {"vendor": "OpenAI", "label": "GPT-5.5", "model": "gpt-5.5", "kind": "api",
                    "build": lambda: OpenAICompatLLM("gpt-5.5", None, okey),
                    "ready": lambda: has_openai},
        "gpt-4.1-nano": {"vendor": "OpenAI", "label": "GPT-4.1-nano", "model": "gpt-4.1-nano", "kind": "api",
                         "build": lambda: OpenAICompatLLM("gpt-4.1-nano", None, okey),
                         "ready": lambda: has_openai},
        # —— 本地大脑(经 Ollama,免费离线;版本号可在 .env 改)——
        "qwen3-vl": {"vendor": "Ollama·本地", "label": "Qwen3-VL 8B", "model": qwen_model, "kind": "local",
                     "build": lambda: OpenAICompatLLM(qwen_model, ollama, "ollama"),
                     "ready": lambda: ollama_ready(qwen_model)},
    }


def list_brains() -> list[dict]:
    """五个大脑清单:名字 + 厂商 + 显示名 + 版本号 + 类型 + 是否配置好(给前端选择器 / 连通自检用)。"""
    return [
        {"name": name, "vendor": spec["vendor"], "label": spec["label"], "model": spec["model"],
         "kind": spec["kind"], "available": spec["ready"]()}
        for name, spec in _registry().items()
    ]


def make_llm(name: str | None = None) -> LLM:
    name = name or DEFAULT_BRAIN
    reg = _registry()
    if name not in reg:
        raise KeyError(f"未知大脑:{name}。可选:{', '.join(reg)}")
    return reg[name]["build"]()
