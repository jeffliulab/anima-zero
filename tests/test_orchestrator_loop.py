"""决策心脏测试：orchestrator 的 ReAct 主循环（handle / handle_stream）。

v0.5 重构起大脑无技能/行为树：主循环 = 看→想→(过安全闸)→动→再看 的闭环 + 工具分发
（世界动作 / 服务顾问按来源路由）+ max_steps 收口 + handle 与 handle_stream 行为一致。
用假 LLM/世界/服务，确定性、不联网。
"""
from __future__ import annotations

from anima import messages
from anima.core.awi import ActionResult, Capabilities, Observation, ToolSpec
from anima.llm import LLMReply, ToolCall
from anima.core.orchestrator import Orchestrator
from anima.clients.registry import WorldRegistry
from anima.session import SessionStore


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

    def invoke(self, name, *, _on_progress=None, _should_abort=None, **a):
        # World 协议的客户端旁路参数（进度/取消）：假世界按协议接受并忽略
        self.invoked.append((name, a))
        return ActionResult(True, f"did {name}")


class _ProgressWorld(_CountWorld):
    """慢动作世界：invoke 时报两次进度（验证流式 progress 事件）。"""

    def invoke(self, name, *, _on_progress=None, _should_abort=None, **a):
        if _on_progress is not None:
            _on_progress("已夹取", 0.5, 1.0)
            _on_progress("正在移向 e4", 0.8, 1.0)
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


def _orch(tmp_path, world):
    reg = WorldRegistry()
    reg._worlds[world.name] = world
    store = SessionStore(root=str(tmp_path))
    orch = Orchestrator(reg, store)
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
    assert messages.MAX_STEPS_REPLY in out["reply"]
    assert world.n_perceive == 2 and len(world.invoked) == 2, "正好转 max_steps 轮"


def test_handle_pure_chat_without_world(tmp_path):
    # 没连世界 → 纯聊天：不 perceive、直接出文字
    reg = WorldRegistry()
    store = SessionStore(root=str(tmp_path))
    orch = Orchestrator(reg, store)
    session, _ = store.new(None, "fake")
    llm = _SeqLLM([LLMReply(text="纯聊天")])
    out = orch.handle(session, "hi", llm)
    assert out["reply"] == "纯聊天"


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
    # 流式路径的工具结果也要进会话历史（后台线程里执行，别丢档）
    msgs = orch.store.get(session.id).messages
    assert any(m.get("role") == "tool" and m.get("name") == "ping" for m in msgs)


def test_handle_stream_forwards_progress_events(tmp_path):
    """长动作进度：世界 invoke 报进度 → 聊天流里实时出现 progress 事件（不黑等）。"""
    world = _ProgressWorld(tool_name="move", tool_kind="tool")
    orch, session = _orch(tmp_path, world)
    llm = _SeqLLM([
        LLMReply(tool_calls=[ToolCall("1", "move", {"to": "e4"})]),
        LLMReply(text="ok"),
    ])
    events = list(orch.handle_stream(session, "动一下", llm))
    prog = [e for e in events if e["type"] == "progress"]
    assert [p["message"] for p in prog] == ["已夹取", "正在移向 e4"]
    i_call = next(i for i, e in enumerate(events) if e["type"] == "tool_call")
    i_res = next(i for i, e in enumerate(events) if e["type"] == "tool_result")
    assert all(i_call < events.index(p) < i_res for p in prog), "进度事件夹在调用与结果之间"


# ---------------------------------------------------------- vision gate / 视觉闸 ----

class _ImageWorld(_CountWorld):
    """带画面的假世界：perceive 总返回一张图。"""

    def perceive(self):
        self.n_perceive += 1
        return Observation(image_png=b"\x89PNG-fake", state={"phase": "idle"})


class _ImageRecordingLLM(_SeqLLM):
    """记下每次 chat 收到的 image，视觉可配。"""

    def __init__(self, replies, vision):
        super().__init__(replies)
        self.vision = vision
        self.seen_images: list = []

    def chat(self, system, history, tools, image):
        self.seen_images.append(image)
        return super().chat(system, history, tools, image)


def test_a_brain_without_eyes_is_not_sent_pictures(tmp_path):
    """⛔ llm.vision=False（纯文本脑，如 demo 的 Qwen3-4B）时主循环不把画面喂给它——
    纯文本模型处理不了 image_url，喂了只会浪费 token 或直接报错。画面照常落会话留痕，
    那是给人看的。"""
    world = _ImageWorld()
    orch, session = _orch(tmp_path, world)
    llm = _ImageRecordingLLM([LLMReply(text="done")], vision=False)
    orch.handle(session, "hi", llm)
    assert llm.seen_images, "主循环一次都没问大脑，测试前提就不成立"
    assert all(img is None for img in llm.seen_images)


def test_a_brain_with_eyes_gets_the_picture(tmp_path):
    """vision=True 的脑照常拿到画面（默认行为不变）。"""
    world = _ImageWorld()
    orch, session = _orch(tmp_path, world)
    llm = _ImageRecordingLLM([LLMReply(text="done")], vision=True)
    orch.handle(session, "hi", llm)
    assert llm.seen_images and llm.seen_images[0] == b"\x89PNG-fake"
