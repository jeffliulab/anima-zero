"""安全门测试：动作下发世界之前那道确定性闸（不经 LLM）。

Wave 6 安全网：钉住「会改世界的动作要过闸、只读动作不过闸」这条不变量，
既单测 SafetyGate 本身，也验证它在 orchestrator 主循环里的正反集成。
"""
from __future__ import annotations

from anima.awi import ActionResult, Capabilities, Observation, ToolSpec
from anima.behavior import RunnerManager
from anima.llm import LLMReply, ToolCall
from anima.orchestrator import Orchestrator
from anima.registry import WorldRegistry
from anima.safety import SafetyGate
from anima.session import SessionStore


class _World:
    name = "w"
    base = "fake://w"

    def __init__(self, tool_name, tool_kind):
        self._tools = [ToolSpec(tool_name, "d", {}, tool_kind)]
        self.invoked: list[str] = []

    def capabilities(self):
        return Capabilities(self.name, "t", self._tools)

    def perceive(self):
        return Observation(image_png=None, state={})

    def invoke(self, name, **a):
        self.invoked.append(name)
        return ActionResult(True, "ok")


class _OneShotLLM:
    vision = False
    model = "fake"

    def __init__(self, tool_name):
        self._tool = tool_name
        self._done = False

    def chat(self, system, history, tools, image):
        if self._done:
            return LLMReply(text="收尾")
        self._done = True
        return LLMReply(tool_calls=[ToolCall("1", self._tool, {})])


def _orch(tmp_path, world, gate):
    reg = WorldRegistry()
    reg._worlds[world.name] = world
    store = SessionStore(root=str(tmp_path))
    orch = Orchestrator(reg, store, safety=gate, runs=RunnerManager())
    session, _ = store.new(world.name, "fake")
    return orch, session


# ---------- SafetyGate 单元 ----------
def test_gate_default_allow_passes():
    ok, reason = SafetyGate(default_allow=True).check(None, "move", {})
    assert ok and reason == ""


def test_gate_default_deny_blocks():
    ok, reason = SafetyGate(default_allow=False).check(None, "move", {})
    assert not ok and reason, "拒绝时要带原因"


# ---------- 三档（allow / approve / deny） ----------
def test_gate_tiers_decide():
    g = SafetyGate(default_allow=True, needs_approval=("place_piece",), blocked=("self_destruct",))
    assert g.decide(None, "look", {}) == "allow"
    assert g.decide(None, "place_piece", {}) == "approve", "需人批动作 → approve"
    assert g.decide(None, "self_destruct", {}) == "deny", "硬拦动作 → deny"


def test_gate_approve_tier_blocks_in_sync_loop():
    ok, reason = SafetyGate(needs_approval=("place_piece",)).check(None, "place_piece", {})
    assert not ok and "人工批准" in reason, "approve 档在同步主循环里先拦下并说明"


def test_gate_blocked_tier_hard_denies():
    ok, reason = SafetyGate(blocked=("x",)).check(None, "x", {})
    assert not ok and "拦截" in reason


# ---------- 在主循环里的集成（正反） ----------
def test_mutating_tool_blocked_when_gate_denies(tmp_path):
    world = _World("move", "tool")                       # 会改世界
    orch, session = _orch(tmp_path, world, SafetyGate(default_allow=False))
    out = orch.handle(session, "走一步", _OneShotLLM("move"))
    assert world.invoked == [], "被安全门拦下 → 绝不下发世界"
    res = out["trace"]["thinking"][0]["tool_results"][0]
    assert res["ok"] is False and "安全闸拦截" in res["message"]


def test_mutating_tool_allowed_when_gate_allows(tmp_path):
    world = _World("move", "tool")
    orch, session = _orch(tmp_path, world, SafetyGate(default_allow=True))
    orch.handle(session, "走一步", _OneShotLLM("move"))
    assert world.invoked == ["move"], "放行 → 正常下发"


def test_readonly_tool_bypasses_gate_even_when_deny(tmp_path):
    world = _World("look", "read")                       # 只读 → 不过闸
    orch, session = _orch(tmp_path, world, SafetyGate(default_allow=False))
    orch.handle(session, "看一眼", _OneShotLLM("look"))
    assert world.invoked == ["look"], "read/judge 类不改世界 → 即使默认拒绝也不拦"


def test_approval_tier_blocks_in_main_loop(tmp_path):
    world = _World("place", "tool")
    gate = SafetyGate(default_allow=True, needs_approval=("place",))   # place 需人批
    orch, session = _orch(tmp_path, world, gate)
    out = orch.handle(session, "放一个", _OneShotLLM("place"))
    assert world.invoked == [], "需人批的动作在同步主循环里先被拦下、不下发世界"
    res = out["trace"]["thinking"][0]["tool_results"][0]
    assert res["ok"] is False and "人工批准" in res["message"]


def test_stream_path_also_blocks(tmp_path):
    world = _World("move", "tool")
    orch, session = _orch(tmp_path, world, SafetyGate(default_allow=False))
    events = list(orch.handle_stream(session, "走一步", _OneShotLLM("move")))
    assert world.invoked == [], "stream 版同样要拦"
    blocked = [e for e in events if e["type"] == "tool_result" and e["ok"] is False]
    assert blocked and "安全闸拦截" in blocked[0]["message"]
