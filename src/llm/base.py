"""LLM 层的接口与中立类型。各 provider 把这套中立历史翻译成自家格式。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..awi import ToolSpec

# 一次回复的最大 token 数(可用 ANIMA_MAX_TOKENS 覆盖);两个 provider 共用,行为对称。
MAX_TOKENS = int(os.getenv("ANIMA_MAX_TOKENS", "1024"))


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMReply:
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


# 中立对话历史 item(各 provider 自己翻译成自家格式):
#   {"role": "user", "text": ...}
#   {"role": "assistant", "text": ..., "tool_calls": [ToolCall, ...]}
#   {"role": "tool", "id": ..., "name": ..., "content": ...}
class LLM(Protocol):
    vision: bool
    model: str

    def chat(
        self,
        system: str,
        history: list[dict],
        tools: list[ToolSpec],
        image_png: bytes | None,
    ) -> LLMReply: ...
