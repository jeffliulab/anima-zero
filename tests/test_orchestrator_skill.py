"""阶段2：orchestrator 作为【元控制器】的 skill 生命周期测试（用假 LLM/世界/技能，确定性、不联网）。

证明（与棋无关，纯框架）：
- 世界支持某 skill 的 required_action 时，才把它列为可进入；enter_skill 工具被大脑调用 → 启动该 skill 的 run。
- 对弈中路由：暂停/恢复/退出/回答 都正确作用到 run（意图用结构化枚举，假 LLM 直接给 JSON）。
"""
from __future__ import annotations

import py_trees
from py_trees.common import Status

from anima import messages
from anima.awi import ActionResult, Capabilities, Observation, ToolSpec
from anima.behavior import BehaviorRunner, Blackboard, RunnerManager
from anima.llm import LLMReply, ToolCall
from anima.orchestrator import ENTER_SKILL_TOOL, Orchestrator
from anima.registry import WorldRegistry
from anima.session import SessionStore
from anima.skill import Skill, SkillRegistry


class _FakeWorld:
    name = "fakeworld"
    base = "fake://w"

    def __init__(self, has_move=True):
        self._tools = [ToolSpec("move", "落子", {}, "tool")] if has_move else []

    def capabilities(self):
        return Capabilities(self.name, "t", self._tools)

    def perceive(self):
        return Observation(image_png=None, state={})

    def invoke(self, name, **a):
        return ActionResult(True, "ok")


class _NoOp(py_trees.behaviour.Behaviour):
    def update(self):
        return Status.RUNNING                      # 永远 RUNNING → run 保持活跃（不自然结束）


class _FakeLLM:
    vision = False
    model = "fake"

    def __init__(self):
        self.reply = LLMReply(text="ok")           # 每个测试按需改写

    def chat(self, system, history, tools, image):
        return self.reply


def _fake_skill() -> Skill:
    def launch(skill, world, llm, role=None):
        bb = Blackboard(world=None)
        return {"ok": True, "runner": BehaviorRunner(bb, _NoOp("noop"), tick_s=0.01),
                "display_name": skill.display_name, "my_side": "white", "opponent": "bot"}
    return Skill(id="testgame", display_name="测试对弈", instructions="i",
                 game_name="测试棋", required_action="move", launcher=launch, adapter_id="testgame")


def _orch(tmp_path, has_move=True):
    reg = WorldRegistry()
    world = _FakeWorld(has_move=has_move)
    reg._worlds["fakeworld"] = world               # 直接注入假世界（绕过 RemoteWorld 的 HTTP）
    store = SessionStore(root=str(tmp_path))
    skills = SkillRegistry()
    skills.register(_fake_skill())
    orch = Orchestrator(reg, store, skills=skills, runs=RunnerManager())
    session, _ = store.new("fakeworld", "fake")
    return orch, session, world, _FakeLLM()


def test_enter_skill_tool_offered_only_when_world_supports(tmp_path):
    orch, session, world, _ = _orch(tmp_path, has_move=True)
    assert [s.id for s in orch._launchable(world)] == ["testgame"]
    assert orch._enter_skill_tool(world) and orch._enter_skill_tool(world)[0].name == ENTER_SKILL_TOOL

    orch2, _, world2, _ = _orch(tmp_path, has_move=False)
    assert orch2._launchable(world2) == [], "世界没有 move 能力 → 不该列为可进入"
    assert orch2._enter_skill_tool(world2) == []


def test_llm_calls_enter_skill_starts_the_run(tmp_path):
    orch, session, world, llm = _orch(tmp_path)
    llm.reply = LLMReply(tool_calls=[ToolCall("1", ENTER_SKILL_TOOL, {"skill_id": "testgame"})])
    out = orch.handle(session, "咱们来一盘", llm)
    try:
        assert "测试对弈" in out["reply"], "应回进入确认语"
        run = orch.active_run(session.id)
        assert run is not None and not run.finished, "应已启动该 skill 的 run"
        assert orch._active_skill[session.id].id == "testgame"
    finally:
        orch.stop_run(session.id)


def test_route_in_skill_exit(tmp_path):
    # 暂停/恢复已不在 orchestrator 路由（改成 world 能力 + 树跟 phase 反应）；route_in_skill 只剩通用的退出/闲聊。
    orch, session, world, llm = _orch(tmp_path)
    assert orch.enter(session, "testgame", llm)["ok"]
    run = orch.active_run(session.id)
    try:
        llm.reply = LLMReply(text='{"intent":"exit"}')
        orch.route_in_skill(session, "不下了", llm)
        assert run.bb.cancelled is True, "退出意图应取消 run"
    finally:
        orch.stop_run(session.id)


def test_route_in_skill_no_longer_classifies_pause(tmp_path):
    # 防回归：pause/resume 不再是 orchestrator 的 in-skill 意图（否则就是把游戏控制硬编码回了 orchestrator）
    from anima.orchestrator import _IN_SKILL_INTENTS
    assert "pause" not in _IN_SKILL_INTENTS and "resume" not in _IN_SKILL_INTENTS
    assert set(_IN_SKILL_INTENTS) == {"exit", "chat"}


def test_route_in_skill_message_answers_pending_question(tmp_path):
    orch, session, world, llm = _orch(tmp_path)
    assert orch.enter(session, "testgame", llm)["ok"]
    run = orch.active_run(session.id)
    try:
        run.bb.pending_question = {"id": 1, "text": "执白还是执黑？", "options": None}
        run.bb.paused = True
        out = orch.route_in_skill(session, "执白", llm)        # 有待答问题时，这句=答案（不走意图分类）
        assert out["ok"]
        assert run.bb.answer == "执白", "应把这句回填为对问题的回答"
        assert run.bb.paused is False, "回答后解除挂起"
    finally:
        orch.stop_run(session.id)


def test_transcript_folded_into_chat_on_finish(tmp_path):
    orch, session, world, llm = _orch(tmp_path)
    assert orch.enter(session, "testgame", llm)["ok"]
    run = orch.active_run(session.id)
    run.bb.emit("anima", "我走 e4")
    run.bb.emit("opponent", "对手走 e5")
    run.bb.finished = True                                   # 模拟对局结束（终局/退出后）
    orch.finalize_if_done(session.id)
    msgs = orch.store.get(session.id).messages
    blocks = [m for m in msgs if m.get("skill_transcript")]
    assert len(blocks) == 1, "结束应把整盘记录折进主聊天，正好一块"
    assert "技能开始" in blocks[0]["text"] and "技能结束" in blocks[0]["text"]
    assert "我走 e4" in blocks[0]["text"] and "对手走 e5" in blocks[0]["text"]
    orch.finalize_if_done(session.id)                        # 幂等：再调不重复落档
    again = [m for m in orch.store.get(session.id).messages if m.get("skill_transcript")]
    assert len(again) == 1
    orch.stop_run(session.id)


def test_exit_via_say_closes_run_and_folds_with_end_line(tmp_path):
    # M1 回归：说"不下了"退出 → run 被移除（面板会关）+ 落档含结束语（树没机会 DoExit，stop_run 补上）
    orch, session, world, llm = _orch(tmp_path)
    assert orch.enter(session, "testgame", llm)["ok"]
    run = orch.active_run(session.id)
    run.bb.emit("anima", "我走 e4")
    llm.reply = LLMReply(text='{"intent":"exit"}')
    out = orch.route_in_skill(session, "不下了", llm)
    assert out["ok"]
    assert orch.active_run(session.id) is None, "退出后 run 应被移除（前端轮询 active=False、面板关闭）"
    blocks = [m for m in orch.store.get(session.id).messages if m.get("skill_transcript")]
    assert len(blocks) == 1, "退出应把整盘折进主聊天，正好一块"
    assert messages.SKILL_EXIT_REPLY in blocks[0]["text"], "落档应含结束语（M1 的核心）"
    assert "我走 e4" in blocks[0]["text"]
    assert "技能结束" in blocks[0]["text"]
