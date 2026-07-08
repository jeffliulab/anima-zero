"""会话核心任务（v0.7）：LLM 自管的工作记忆寄存器。

覆盖：元工具登记/改写/清除 → store 落盘 + 世界零打扰；常驻块注入系统提示（含纯聊天）；
空任务拒绝；与世界工具同名时元工具让位；旧会话 JSON（无字段）加载兼容；summary 暴露字段。
用假 LLM/世界，确定性、不联网（夹具与 test_orchestrator_loop 同款）。
"""
from __future__ import annotations

import json
import os

from anima import messages
from anima.core.awi import ActionResult, Capabilities, Observation, ToolSpec
from anima.llm import LLMReply, ToolCall
from anima.core.orchestrator import Orchestrator
from anima.clients.registry import WorldRegistry
from anima.session import Session, SessionStore


class _World:
    name = "w"
    base = "fake://w"

    def __init__(self, tool_name="ping", tool_kind="read"):
        self._tools = [ToolSpec(tool_name, "原子能力", {}, tool_kind)]
        self.invoked: list[tuple[str, dict]] = []

    def capabilities(self):
        return Capabilities(self.name, "t", self._tools)

    def perceive(self):
        return Observation(image_png=None, state={})

    def invoke(self, name, *, _on_progress=None, _should_abort=None, **a):
        self.invoked.append((name, a))
        return ActionResult(True, f"did {name}")


class _SeqLLM:
    """假 LLM：按序吐回复，并记录每次收到的 system（验证常驻块注入）。"""
    vision = False
    model = "fake"

    def __init__(self, replies):
        self._replies = list(replies)
        self._i = 0
        self.systems: list[str] = []

    def chat(self, system, history, tools, image):
        self.systems.append(system)
        r = self._replies[min(self._i, len(self._replies) - 1)]
        self._i += 1
        return r


def _orch(tmp_path, world):
    reg = WorldRegistry()
    if world is not None:
        reg._worlds[world.name] = world
    store = SessionStore(root=str(tmp_path))
    orch = Orchestrator(reg, store)
    session, _ = store.new(world.name if world else None, "fake")
    return orch, session


def test_set_core_task_persists_and_injects(tmp_path):
    world = _World()
    orch, session = _orch(tmp_path, world)
    llm = _SeqLLM([
        LLMReply(tool_calls=[ToolCall("1", "set_core_task", {"task": "把桌子整理完"})]),
        LLMReply(text="登记好了"),
    ])
    out = orch.handle(session, "帮我把桌子整理完，可能要很多步", llm)
    assert out["reply"] == "登记好了"
    assert orch.store.get(session.id).core_task == "把桌子整理完"
    assert world.invoked == [], "元工具不该打扰世界"
    # 登记后的下一步，system 里有常驻块
    assert "把桌子整理完" in llm.systems[-1] and "核心任务" in llm.systems[-1]
    # 回执落会话历史（role=tool）
    msgs = orch.store.get(session.id).messages
    assert any(m.get("role") == "tool" and m.get("name") == "set_core_task"
               and "把桌子整理完" in m.get("content", "") for m in msgs)


def test_core_task_survives_turns_and_rewrite_and_clear(tmp_path):
    world = _World()
    orch, session = _orch(tmp_path, world)
    orch.handle(session, "开始任务", _SeqLLM([
        LLMReply(tool_calls=[ToolCall("1", "set_core_task", {"task": "任务 A"})]),
        LLMReply(text="ok")]))
    # 下一轮（新的 handle）：常驻块还在——这就是「我走完了」这种短触发词能工作的机制
    llm2 = _SeqLLM([LLMReply(tool_calls=[ToolCall("2", "set_core_task", {"task": "任务 A（已完成一半）"})]),
                    LLMReply(text="继续中")])
    orch.handle(session, "继续", llm2)
    assert "任务 A" in llm2.systems[0], "跨轮注入：第二轮第一步就该看到核心任务"
    assert orch.store.get(session.id).core_task == "任务 A（已完成一半）", "重复登记=改写"
    orch.handle(session, "收工", _SeqLLM([
        LLMReply(tool_calls=[ToolCall("3", "clear_core_task", {})]),
        LLMReply(text="收工")]))
    assert orch.store.get(session.id).core_task == ""


def test_empty_task_refused(tmp_path):
    world = _World()
    orch, session = _orch(tmp_path, world)
    out = orch.handle(session, "x", _SeqLLM([
        LLMReply(tool_calls=[ToolCall("1", "set_core_task", {"task": "  "})]),
        LLMReply(text="fin")]))
    assert orch.store.get(session.id).core_task == ""
    results = out["trace"]["thinking"][0]["tool_results"]
    assert results[0]["ok"] is False


def test_pure_chat_also_supports_core_task(tmp_path):
    orch, session = _orch(tmp_path, None)
    llm = _SeqLLM([LLMReply(tool_calls=[ToolCall("1", "set_core_task", {"task": "写一篇长文"})]),
                   LLMReply(text="记下了")])
    out = orch.handle(session, "帮我写一篇长文", llm)
    assert out["reply"] == "记下了"
    assert orch.store.get(session.id).core_task == "写一篇长文"
    assert "写一篇长文" in llm.systems[-1]


def test_name_collision_world_wins_meta_yields(tmp_path):
    world = _World(tool_name="set_core_task", tool_kind="tool")   # 世界抢注了同名工具
    orch, session = _orch(tmp_path, world)
    out = orch.handle(session, "x", _SeqLLM([
        LLMReply(tool_calls=[ToolCall("1", "set_core_task", {"task": "t"})]),
        LLMReply(text="fin")]))
    assert world.invoked and world.invoked[0][0] == "set_core_task", "同名时元工具让位，调用应到世界"
    assert orch.store.get(session.id).core_task == "", "寄存器不该被碰"


def test_old_session_json_without_field_loads(tmp_path):
    store = SessionStore(root=str(tmp_path))
    old = {"id": "s_1", "world": None, "brain": "b", "status": "active",
           "created_at": "t", "title": "旧会话", "messages": []}
    with open(os.path.join(str(tmp_path), "s_1.json"), "w", encoding="utf-8") as f:
        json.dump(old, f)
    s = store.load("s_1")
    assert s.core_task == ""
    assert s.summary()["core_task"] == ""      # summary 暴露字段（UI 透明）


def test_meta_tools_on_toolsheet(tmp_path):
    """工具单里有两件元工具（LLM 能看到才可能调用）。"""
    world = _World()
    orch, session = _orch(tmp_path, world)
    llm = _SeqLLM([LLMReply(text="hi")])
    orch.handle(session, "在吗", llm)
    # _SeqLLM 只记了 system；改从消息面验证：直接构建一次工具单
    tools = orch._meta_toolbox(set())
    assert {t.name for t in tools} == {messages.CORE_TASK_SET_TOOL["name"],
                                       messages.CORE_TASK_CLEAR_TOOL["name"]}


def test_context_sanitizes_orphan_tool_calls():
    """结对完整性（v0.7）：孤儿 tool_call 补占位结果；窗口开头无主 tool 结果被丢弃。
    背景：进程在「调用落档、结果未落」间被杀 → 此后每轮 provider 400、会话报废（2026-07-06 实锤）。"""
    from anima import messages as msgs
    from anima.session import context
    history = [
        {"role": "tool", "id": "t0", "name": "x", "content": "无主结果（assistant 已滑出）"},
        {"role": "user", "text": "开始"},
        {"role": "assistant", "text": "", "tool_calls": [{"id": "t1", "name": "move", "arguments": {}}]},
        # t1 的结果因中断丢失
        {"role": "user", "text": "继续"},
    ]
    out = context.build(history, token_budget=10_000)
    assert out[0]["role"] == "user", "开头无主 tool 结果应被丢弃"
    tools = [m for m in out if m["role"] == "tool"]
    assert len(tools) == 1 and tools[0]["id"] == "t1"
    assert tools[0]["content"] == msgs.ORPHAN_TOOL_RESULT
    # 有配对结果时不多补
    history2 = [
        {"role": "assistant", "text": "", "tool_calls": [{"id": "a", "name": "move", "arguments": {}}]},
        {"role": "tool", "id": "a", "name": "move", "content": "ok"},
    ]
    out2 = context.build(history2, token_budget=10_000)
    assert sum(1 for m in out2 if m["role"] == "tool") == 1
