"""上下文构建:从会话记录里挑一部分发给大脑(5.1 主线:上下文是稀缺资源)。

- 丢掉感知图条目(只发最新一张,在 orchestrator 里单独附);老图只存不发,省大量 token。
- 滑动窗口:按 token 预算保留最近若干轮(粗略按字符估算 token)。
- 结对完整性清理(v0.7):assistant 的 tool_calls 必须有配对的 tool 结果,否则 provider 会 400——
  ① 进程在「调用已落档、结果还没落」之间崩溃/被杀,会留下孤儿 tool_call(2026-07-06 实锤:
    一次 kill 让会话此后每轮必 400,整个会话报废)→ 补一条「结果因中断丢失」的诚实占位结果;
  ② 滑窗起点可能切在 tool 结果上(它的 assistant 已被挤出窗口)→ 丢掉这些开头的孤儿结果。
- 转成中立历史格式(user / assistant+toolcalls / tool)。

留口(本版先不做,见 plan 第12节):summarize(更早的)接在窗口前;给稳定前缀打 prompt-cache 标记。
"""
from __future__ import annotations

from .. import config, prompts
from ..llm import ToolCall


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

    kept = _sanitize_pairs(kept)

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


def _sanitize_pairs(kept: list[dict]) -> list[dict]:
    """保证 assistant 的每个 tool_call 都有配对的 tool 结果（provider 硬约束）。
    开头无主的 tool 结果 → 丢弃（它的 assistant 已滑出窗口）；
    中间无果的 tool_call → 就地补「结果因中断丢失」占位（诚实说明，不假装成功）。"""
    out: list[dict] = []
    i = 0
    # ① 丢掉窗口开头无主的 tool 结果
    while i < len(kept) and kept[i].get("role") == "tool":
        i += 1
    while i < len(kept):
        m = kept[i]
        out.append(m)
        if m.get("role") == "assistant" and m.get("tool_calls"):
            want = [(t["id"], t["name"]) for t in m["tool_calls"]]
            got: set = set()
            j = i + 1
            while j < len(kept) and kept[j].get("role") == "tool":
                got.add(kept[j].get("id"))
                out.append(kept[j])
                j += 1
            for tid, name in want:                    # ② 无果的调用补诚实占位
                if tid not in got:
                    out.append({"role": "tool", "id": tid, "name": name,
                                "content": prompts.ORPHAN_TOOL_RESULT})
            i = j
        else:
            i += 1
    return out
