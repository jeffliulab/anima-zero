"""跨轮回归（v0.8 补缺）：步数超限 overflow 礼貌停下 →「继续」→ 下一轮从头起、
带核心任务接着做并能收尾。

背景：v0.8 审计 §五登记的缺口——单轮 overflow（test_orchestrator_loop 的
test_handle_max_steps_stops）与核心任务跨轮注入（test_core_task 的
test_core_task_survives_turns_and_rewrite_and_clear）各自有测，但「overflow → 继续」这条
**组合链路**从没测过。回合制铁律的落点正是它：超限不是报错、是**可续的停顿**；核心任务寄存器让
「继续」这种短句足以驱动下一轮接上（目标不随 overflow 蒸发）。用假 LLM/世界，确定性、不联网。
"""
from __future__ import annotations

from anima import messages
from anima.core.awi import ActionResult, Capabilities, Observation, ToolSpec
from anima.llm import LLMReply, ToolCall
from anima.core.orchestrator import Orchestrator
from anima.clients.registry import WorldRegistry
from anima.session import SessionStore


class _World:
    """假世界：记 perceive/invoke 次数；只有一个只读 ping 工具。"""
    name = "w"
    base = "fake://w"

    def __init__(self):
        self._tools = [ToolSpec("ping", "原子能力", {}, "read")]
        self.n_perceive = 0
        self.invoked: list[tuple[str, dict]] = []

    def capabilities(self):
        return Capabilities(self.name, "t", self._tools)

    def perceive(self):
        self.n_perceive += 1
        return Observation(image_png=None, state={})

    def invoke(self, name, *, _on_progress=None, _should_abort=None, **a):
        self.invoked.append((name, a))
        return ActionResult(True, f"did {name}")


class _SeqLLM:
    """假 LLM：按序吐回复（用尽后重复最后一条，方便测 overflow），并记录每次收到的 system
    （验证核心任务跨轮注入）。"""
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
    reg._worlds[world.name] = world
    store = SessionStore(root=str(tmp_path))
    orch = Orchestrator(reg, store)
    session, _ = store.new(world.name, "fake")
    return orch, session


def test_overflow_pause_then_continue_resumes_with_core_task(tmp_path):
    """整条链：turn1 登记核心任务后步数超限→礼貌停下；turn2「继续」从 step=0 重起、
    第一步就仍带核心任务、并能收尾——证明 overflow 是可续停顿而非终态，寄存器跨越 overflow 边界。"""
    world = _World()
    orch, session = _orch(tmp_path, world)

    # ── turn 1：登记「找到厨房」后一直动作（不出文字）→ max_steps=2 撞顶 → overflow ──
    llm1 = _SeqLLM([
        LLMReply(tool_calls=[ToolCall("1", "set_core_task", {"task": "找到厨房"})]),
        LLMReply(tool_calls=[ToolCall("2", "ping", {})]),   # 之后用尽即重复本条=一直动作
    ])
    out1 = orch.handle(session, "去厨房，可能要找一会儿", llm1, max_steps=2)
    assert out1["reply"] == messages.MAX_STEPS_REPLY, "超限=礼貌停顿（可续），不是错误/终态"
    assert orch.store.get(session.id).core_task == "找到厨房", "任务寄存器在停顿后仍在册"
    perceived_turn1 = world.n_perceive
    assert perceived_turn1 == 2, "turn1 正好转 max_steps=2 轮"

    # ── turn 2：用户说「继续」→ 新一轮从 step=0 起，做一步动作后出文字收尾 ──
    llm2 = _SeqLLM([
        LLMReply(tool_calls=[ToolCall("3", "ping", {})]),
        LLMReply(text="到厨房了"),
    ])
    out2 = orch.handle(session, "继续", llm2)   # 默认 max_steps 充裕
    # 跨越 overflow 边界：续轮**第一步**的 system 就带核心任务（「继续」这种短句靠它驱动接上）
    assert "找到厨房" in llm2.systems[0] and "Core task" in llm2.systems[0], "续轮首步即注入核心任务"
    assert out2["reply"] == "到厨房了", "overflow 是停顿：下一轮能接着做并收尾（未漏带步数计数致又立刻停）"
    assert world.n_perceive > perceived_turn1, "续轮重新感知（step 归零、世界重新看）"


def test_overflow_pause_and_resume_in_stream_path(tmp_path):
    """流式路径同样成立：turn1 超限时 reply 事件=可续停顿语、流以 done 收尾；turn2「继续」能流式收尾。
    UI 走 handle_stream，回合制的「停顿→继续」必须在流里也如此表现。"""
    world = _World()
    orch, session = _orch(tmp_path, world)

    llm1 = _SeqLLM([LLMReply(tool_calls=[ToolCall("1", "ping", {})])])   # 永远动作 → 撞顶
    ev1 = list(orch.handle_stream(session, "一直走", llm1, max_steps=2))
    replies1 = [e for e in ev1 if e["type"] == "reply"]
    assert replies1 and replies1[-1]["text"] == messages.MAX_STEPS_REPLY, "流里最后的 reply=停顿语"
    assert ev1[-1]["type"] == "done", "流以 done 正常收尾（不是异常）"

    llm2 = _SeqLLM([LLMReply(text="好的，停下")])
    ev2 = list(orch.handle_stream(session, "继续", llm2))
    assert any(e["type"] == "reply" and e["text"] == "好的，停下" for e in ev2), "续轮流式收尾正常"
