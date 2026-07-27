"""笔记本（v1.0）：LLM 自管的第二个状态通道。

和核心任务同一套路（LLM 亲自增删、无关键词触发、常驻注入系统提示），区别在**形状**——
核心任务是一句话「我在干什么」，笔记本是一条条「我发现了什么」。

覆盖：加/删 → store 落盘 + 世界零打扰；编号注入系统提示；跨轮不丢；
三种拒绝（空 / 超长 / 记满）都**明说原因不静默处理**；越界编号；旧会话 JSON 兼容；
两个寄存器同时注入互不干扰。用假 LLM/世界，确定性、不联网。
"""
from __future__ import annotations

import json
import os

from anima import config
from anima.clients.registry import WorldRegistry
from anima.core.awi import ActionResult, Capabilities, Observation, ToolSpec
from anima.core.orchestrator import Orchestrator
from anima.llm import LLMReply, ToolCall
from anima.session import SessionStore


class _World:
    name = "w"
    base = "fake://w"

    def __init__(self):
        self._tools = [ToolSpec("ping", "原子能力", {}, "read")]
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


def _orch(tmp_path, world=None):
    reg = WorldRegistry()
    if world is not None:
        reg._worlds[world.name] = world
    store = SessionStore(root=str(tmp_path))
    orch = Orchestrator(reg, store)
    session, _ = store.new(world.name if world else None, "fake")
    return orch, session


def _add(i, text):
    return LLMReply(tool_calls=[ToolCall(str(i), "add_note", {"note": text})])


def test_add_note_persists_and_injects(tmp_path):
    world = _World()
    orch, session = _orch(tmp_path, world)
    llm = _SeqLLM([_add(1, "北边那扇门后面是个有床的房间"), LLMReply(text="记下了")])
    out = orch.handle(session, "看看四周", llm)
    assert out["reply"] == "记下了"
    assert orch.store.get(session.id).notes == ["北边那扇门后面是个有床的房间"]
    assert world.invoked == [], "元工具不该打扰世界"
    # 记完的下一步，system 里带编号的常驻块
    assert "1. 北边那扇门后面是个有床的房间" in llm.systems[-1]
    assert "笔记本" in llm.systems[-1]
    # 回执落会话历史（role=tool）
    msgs = orch.store.get(session.id).messages
    assert any(m.get("role") == "tool" and m.get("name") == "add_note" for m in msgs)


def test_notes_survive_turns_and_drop_by_number(tmp_path):
    world = _World()
    orch, session = _orch(tmp_path, world)
    orch.handle(session, "探索", _SeqLLM([_add(1, "甲"), _add(2, "乙"), _add(3, "丙"),
                                          LLMReply(text="ok")]))
    assert orch.store.get(session.id).notes == ["甲", "乙", "丙"]
    # 下一轮：跨轮注入——第二轮第一步就该看到笔记本
    llm2 = _SeqLLM([LLMReply(tool_calls=[ToolCall("9", "drop_note", {"number": 2})]),
                    LLMReply(text="划掉了")])
    orch.handle(session, "继续", llm2)
    assert "1. 甲" in llm2.systems[0] and "2. 乙" in llm2.systems[0]
    assert orch.store.get(session.id).notes == ["甲", "丙"], "按编号删中间那条，其余保序"
    # 删完重新编号：丙 现在是第 2 条
    assert "2. 丙" in llm2.systems[-1]


def test_empty_note_refused(tmp_path):
    orch, session = _orch(tmp_path, _World())
    out = orch.handle(session, "x", _SeqLLM([_add(1, "   "), LLMReply(text="fin")]))
    assert orch.store.get(session.id).notes == []
    assert out["trace"]["thinking"][0]["tool_results"][0]["ok"] is False


def test_too_long_note_refused_not_truncated(tmp_path):
    """⛔ 超长不截断：截一半的笔记比没有更糟，要明说原因让 LLM 自己缩写。"""
    orch, session = _orch(tmp_path, _World())
    long_note = "很" * (config.NOTE_MAX_CHARS + 1)
    out = orch.handle(session, "x", _SeqLLM([_add(1, long_note), LLMReply(text="fin")]))
    assert orch.store.get(session.id).notes == [], "既没存全，也没存半截"
    r = out["trace"]["thinking"][0]["tool_results"][0]
    assert r["ok"] is False and str(config.NOTE_MAX_CHARS) in r["message"]


def test_full_notebook_refuses_and_says_why(tmp_path):
    """⛔ 记满不静默丢弃：明确告诉 LLM 满了，让它自己划掉没用的。"""
    orch, session = _orch(tmp_path, _World())
    orch.store.set_notes(session.id, [f"第{i}条" for i in range(config.NOTES_MAX)])
    out = orch.handle(session, "x", _SeqLLM([_add(1, "再来一条"), LLMReply(text="fin")]))
    assert len(orch.store.get(session.id).notes) == config.NOTES_MAX, "没被挤掉任何一条"
    r = out["trace"]["thinking"][0]["tool_results"][0]
    assert r["ok"] is False and "drop_note" in r["message"]


def test_drop_out_of_range_reports_total(tmp_path):
    orch, session = _orch(tmp_path, _World())
    orch.store.set_notes(session.id, ["甲", "乙"])
    out = orch.handle(session, "x", _SeqLLM([
        LLMReply(tool_calls=[ToolCall("1", "drop_note", {"number": 5})]), LLMReply(text="fin")]))
    assert orch.store.get(session.id).notes == ["甲", "乙"]
    r = out["trace"]["thinking"][0]["tool_results"][0]
    assert r["ok"] is False and "2" in r["message"]


def test_pure_chat_also_supports_notes(tmp_path):
    orch, session = _orch(tmp_path, None)
    llm = _SeqLLM([_add(1, "用户偏好简短回答"), LLMReply(text="记下了")])
    orch.handle(session, "聊聊", llm)
    assert orch.store.get(session.id).notes == ["用户偏好简短回答"]
    assert "用户偏好简短回答" in llm.systems[-1]


def test_both_registers_inject_together(tmp_path):
    """两个通道同时有内容时都注入，互不覆盖（核心任务在前、笔记在后）。"""
    orch, session = _orch(tmp_path, _World())
    orch.store.set_core_task(session.id, "找到卧室")
    orch.store.set_notes(session.id, ["客厅已看过，没有床"])
    llm = _SeqLLM([LLMReply(text="继续")])
    orch.handle(session, "继续", llm)
    s = llm.systems[0]
    assert "找到卧室" in s and "客厅已看过，没有床" in s
    assert s.index("找到卧室") < s.index("客厅已看过，没有床")


def test_old_session_json_without_field_loads(tmp_path):
    """旧会话 JSON 没有 notes 键也要能加载（Session(**data) 构造，字段必须有默认值）。"""
    store = SessionStore(root=str(tmp_path))
    old = {"id": "s_1", "world": None, "brain": "b", "status": "active",
           "created_at": "t", "title": "旧会话", "core_task": "", "messages": []}
    with open(os.path.join(str(tmp_path), "s_1.json"), "w", encoding="utf-8") as f:
        json.dump(old, f)
    s = store.load("s_1")
    assert s.notes == []
    assert s.summary()["notes"] == []      # summary 暴露字段（UI 透明）


def test_no_notes_no_block(tmp_path):
    """没笔记就完全不注入——空本子不该占系统提示的地方。"""
    orch, session = _orch(tmp_path, _World())
    llm = _SeqLLM([LLMReply(text="hi")])
    orch.handle(session, "在吗", llm)
    assert "笔记本（你自己记的" not in llm.systems[0]
