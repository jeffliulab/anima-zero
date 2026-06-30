"""决策心脏测试：orchestrator 的 ReAct 主循环（handle / handle_stream）。

这是「艰难的 0.2」Wave 6 补的安全网——去棋化重构（T1）之前先把主循环的**行为**钉住：
看→想→(过安全闸)→动→再看 的闭环、工具分发、enter_skill 短路、max_steps 收口、
对局进行中路由到面板、handle 与 handle_stream 行为一致。用假 LLM/世界，确定性、不联网。
"""
from __future__ import annotations

import py_trees
from py_trees.common import Status

from anima.awi import ActionResult, Capabilities, Observation, ToolSpec
from anima.behavior import BehaviorRunner, Blackboard, RunnerManager
from anima.llm import LLMReply, ToolCall
from anima.orchestrator import ENTER_SKILL_TOOL, Orchestrator
from anima.registry import WorldRegistry
from anima.session import SessionStore
from anima.skill import Skill, SkillRegistry


class _CountWorld:
    """假世界：记 capabilities / perceive / invoke 各调了几次；工具种类可配。"""
    name = "countworld"
    base = "fake://c"

    def __init__(self, tool_name="ping", tool_kind="read"):
        self._tools = [ToolSpec(tool_name, "原子能力", {}, tool_kind)]
        self.n_caps = self.n_perceive = 0
        self.invoked: list[tuple[str, dict]] = []

    def capabilities(self):
        self.n_caps += 1
        return Capabilities(self.name, "t", self._tools)

    def perceive(self):
        self.n_perceive += 1
        return Observation(image_png=None, state={"phase": "idle"})

    def invoke(self, name, **a):
        self.invoked.append((name, a))
        return ActionResult(True, f"did {name}")


class _SeqLLM:
    """假 LLM：按列表顺序吐回复；列表用尽后重复最后一条（方便测 max_steps 循环）。"""
    vision = False
    model = "fake"

    def __init__(self, replies):
        self._replies = list(replies)
        self._i = 0
        self.calls = 0

    def chat(self, system, history, tools, image):
        self.calls += 1
        r = self._replies[min(self._i, len(self._replies) - 1)]
        self._i += 1
        return r


class _NoOp(py_trees.behaviour.Behaviour):
    def update(self):
        return Status.RUNNING


def _orch(tmp_path, world, skills=None):
    reg = WorldRegistry()
    reg._worlds[world.name] = world
    store = SessionStore(root=str(tmp_path))
    orch = Orchestrator(reg, store, skills=skills, runs=RunnerManager())
    session, _ = store.new(world.name, "fake")
    return orch, session


def test_handle_text_only_returns_reply(tmp_path):
    world = _CountWorld()
    orch, session = _orch(tmp_path, world)
    llm = _SeqLLM([LLMReply(text="你好，我在。")])
    out = orch.handle(session, "在吗", llm)
    assert out["reply"] == "你好，我在。"
    # 出文字即收尾：只 perceive 了一轮
    assert world.n_perceive == 1
    msgs = orch.store.get(session.id).messages
    assert any(m.get("role") == "assistant" and m.get("text") == "你好，我在。" for m in msgs)


def test_handle_dispatches_tool_then_finishes(tmp_path):
    world = _CountWorld(tool_name="ping", tool_kind="read")
    orch, session = _orch(tmp_path, world)
    llm = _SeqLLM([
        LLMReply(tool_calls=[ToolCall("1", "ping", {"x": 1})]),   # 第1轮：调工具
        LLMReply(text="done"),                                     # 第2轮：出文字收尾
    ])
    out = orch.handle(session, "go", llm)
    assert out["reply"] == "done"
    assert world.invoked == [("ping", {"x": 1})], "工具应被真正下发给世界一次"
    assert world.n_perceive == 2, "闭环：动作后应再感知一轮"
    # trace 里记下了这步的 tool_result
    results = out["trace"]["thinking"][0]["tool_results"]
    assert results == [{"name": "ping", "ok": True, "message": "did ping"}]


def test_handle_max_steps_stops(tmp_path):
    world = _CountWorld(tool_name="ping", tool_kind="read")
    orch, session = _orch(tmp_path, world)
    llm = _SeqLLM([LLMReply(tool_calls=[ToolCall("1", "ping", {})])])  # 永远调工具，不收尾
    out = orch.handle(session, "loop", llm, max_steps=2)
    assert "达到最大步数" in out["reply"]
    assert world.n_perceive == 2 and len(world.invoked) == 2, "正好转 max_steps 轮"


def test_handle_pure_chat_without_world(tmp_path):
    # 没连世界 → 纯聊天：不 perceive、直接出文字
    reg = WorldRegistry()
    store = SessionStore(root=str(tmp_path))
    orch = Orchestrator(reg, store, runs=RunnerManager())
    session, _ = store.new(None, "fake")
    llm = _SeqLLM([LLMReply(text="纯聊天")])
    out = orch.handle(session, "hi", llm)
    assert out["reply"] == "纯聊天"


def _skill_with_noop() -> Skill:
    def launch(skill, world, llm, role=None):
        bb = Blackboard(world=None)
        return {"ok": True, "runner": BehaviorRunner(bb, _NoOp("noop"), tick_s=0.01),
                "display_name": skill.display_name, "my_side": "white", "opponent": "bot"}
    return Skill(id="g", display_name="测试技能", instructions="i",
                 game_name="测试棋", required_action="move", launcher=launch, adapter_id="g")


def test_handle_enter_skill_short_circuits(tmp_path):
    world = _CountWorld(tool_name="move", tool_kind="tool")
    skills = SkillRegistry()
    skills.register(_skill_with_noop())
    orch, session = _orch(tmp_path, world, skills=skills)
    llm = _SeqLLM([LLMReply(tool_calls=[ToolCall("1", ENTER_SKILL_TOOL, {"skill_id": "g"})])])
    try:
        out = orch.handle(session, "来一盘", llm)
        assert "测试技能" in out["reply"], "调 enter_skill 应进入并收尾"
        assert orch.active_run(session.id) is not None
        assert world.invoked == [], "enter_skill 是 orchestrator 拦截、不下发世界"
    finally:
        orch.stop_run(session.id)


def test_handle_routes_to_active_run(tmp_path):
    # run 进行中 → handle 不跑主循环，转去面板路由（route_in_skill）
    world = _CountWorld(tool_name="move", tool_kind="tool")
    skills = SkillRegistry()
    skills.register(_skill_with_noop())
    orch, session = _orch(tmp_path, world, skills=skills)
    assert orch.enter(session, "g", _SeqLLM([LLMReply(text="x")]))["ok"]
    try:
        before = world.n_perceive
        llm = _SeqLLM([LLMReply(text='{"intent":"chat"}'), LLMReply(text="陪聊一句")])
        out = orch.handle(session, "随便说句", llm)
        assert out["reply"], "对局中说话应被路由处理并回话"
        assert world.n_perceive == before, "对局中 handle 不进主循环、不再 perceive"
    finally:
        orch.stop_run(session.id)


def test_handle_stream_mirrors_handle(tmp_path):
    world = _CountWorld(tool_name="ping", tool_kind="read")
    orch, session = _orch(tmp_path, world)
    llm = _SeqLLM([
        LLMReply(tool_calls=[ToolCall("1", "ping", {})]),
        LLMReply(text="done"),
    ])
    events = list(orch.handle_stream(session, "go", llm))
    types = [e["type"] for e in events]
    assert types[0] == "start" and types[-1] == "done"
    assert "perception" in types and "tool_call" in types and "tool_result" in types
    assert any(e["type"] == "reply" and e["text"] == "done" for e in events)
    assert world.invoked == [("ping", {})], "stream 版也应真正下发工具"
