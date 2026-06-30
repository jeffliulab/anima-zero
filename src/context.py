"""上下文构建:从会话记录里挑一部分发给大脑(5.1 主线:上下文是稀缺资源)。

- 丢掉感知图条目(只发最新一张,在 orchestrator 里单独附);老图只存不发,省大量 token。
- 滑动窗口:按 token 预算保留最近若干轮(粗略按字符估算 token)。
- 转成中立历史格式(user / assistant+toolcalls / tool)。

留口(本版先不做,见 plan 第12节):summarize(更早的)接在窗口前;给稳定前缀打 prompt-cache 标记。
"""
from __future__ import annotations

from . import config
from .llm import ToolCall


def _est_tokens(s: str) -> int:
    return max(1, len(s) // 3)  # 粗估:中英混合约 3 字符 ≈ 1 token


def _entry_text(m: dict) -> str:
    role = m.get("role")
    if role == "user":
        return m.get("text", "")
    if role == "assistant":
        return (m.get("text", "") or "") + "".join(str(t) for t in m.get("tool_calls", []))
    if role == "tool":
        return m.get("content", "")
    return ""


def build(messages: list[dict], token_budget: int | None = None) -> list[dict]:
    if token_budget is None:
        token_budget = config.CONTEXT_TOKEN_BUDGET
    convo = [m for m in messages if m.get("role") != "perception"]  # 图不重发

    # 滑动窗口:从最近往前累计到预算
    kept: list[dict] = []
    total = 0
    for m in reversed(convo):
        t = _est_tokens(_entry_text(m))
        if total + t > token_budget and kept:
            break
        kept.append(m)
        total += t
    kept.reverse()

    # 转中立格式
    out: list[dict] = []
    for m in kept:
        role = m["role"]
        if role == "user":
            out.append({"role": "user", "text": m["text"]})
        elif role == "assistant":
            tcs = [ToolCall(t["id"], t["name"], t.get("arguments", {})) for t in m.get("tool_calls", [])]
            out.append({"role": "assistant", "text": m.get("text", ""), "tool_calls": tcs})
        elif role == "tool":
            out.append({"role": "tool", "id": m["id"], "name": m["name"], "content": m["content"]})
    return out
