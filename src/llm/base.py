"""LLM 层的接口与中立类型。各 provider 把这套中立历史翻译成自家格式。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .. import config
from ..awi import ToolSpec

# 一次回复的最大 token 数（config，env ANIMA_MAX_TOKENS 可覆盖）;两个 provider 共用,行为对称。
MAX_TOKENS = config.MAX_TOKENS


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMReply:
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    # token 用量（各 provider 从响应里取，归一成 {"input","output","total"}；拿不到=None）。给 anima-logs 算成本/防上下文爆。
    usage: dict[str, int] | None = None


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
