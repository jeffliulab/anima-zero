"""旗舰链路测试：「LLM 亲自下一步棋」的完整回合（无 game mode、无行为树）。

剧本（FakeLLM 三步）：用户"该你了" →
  第1步 LLM 调 best_move(fen=…)（服务工具，路由给引擎顾问）→ 结果进历史(role=tool)
  第2步 LLM 调 move(from,to)（世界工具，过安全闸后发世界）→ 结果进历史
  第3步 LLM 出文字回复
断言：调用去向正确、历史顺序正确、llm_call 留痕带会话标签。
（service_call/world_call 的入账在 test_session_log / test_services_mount 各自单测；
 真三方合流的日志链走端到端手工验收。）
"""
from __future__ import annotations

from anima import session_log
from anima.awi import ActionResult, Capabilities, Observation, ToolSpec
from anima.llm import LLMReply, ToolCall
from anima.orchestrator import Orchestrator
from anima.registry import WorldRegistry
from anima.session import SessionStore

START_FEN = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"


class _ChessWorld:
    """假棋盘世界：只有一个 move 工具（kind=tool，会改世界→过安全闸），感知只给画面。"""
    name = "sim-chess"
    base = "fake://chess"

    def __init__(self):
        self.invoked: list[tuple[str, dict]] = []

    def capabilities(self):
        return Capabilities(self.name, "t", [ToolSpec(
            "move", "把一个子从 from 走到 to",
            {"type": "object", "properties": {"from": {"type": "string"}, "to": {"type": "string"}}}, "tool")])

    def perceive(self):
        return Observation(image_png=b"\x89PNG-fake", state={})

    def invoke(self, name, *, _on_progress=None, _should_abort=None, **a):
        # World 协议的客户端旁路参数（进度/取消）：假世界按协议接受并忽略
        self.invoked.append((name, a))
        return ActionResult(True, "已走 e7e5")


class _Engine:
    """假引擎顾问：形状与 RemoteService 一致（工具 kind=read）。"""
    name = "chess-engine"

    def __init__(self):
        self.invoked: list[tuple[str, dict]] = []

    def capabilities(self):
        return Capabilities(self.name, "s", [ToolSpec(
            "best_move", "给 FEN 返回最佳着法（UCI）",
            {"type": "object", "properties": {"fen": {"type": "string"}}}, "read")])

    def invoke(self, name, **a):
        self.invoked.append((name, a))
        return ActionResult(True, "e7e5", data={"result": "e7e5"})


class _ScriptLLM:
    vision = True
    model = "fake-brain"

    def __init__(self):
        self._script = [
            LLMReply(tool_calls=[ToolCall("1", "best_move", {"fen": START_FEN})]),
            LLMReply(tool_calls=[ToolCall("2", "move", {"from": "e7", "to": "e5"})]),
            LLMReply(text="我走了 e7e5，该你了。"),
        ]
        self.images_seen = 0
        self.calls = 0

    def chat(self, system, history, tools, image):
        self.calls += 1
        if image is not None:
            self.images_seen += 1
        return self._script[min(self.calls - 1, len(self._script) - 1)]


def test_llm_plays_one_turn_via_engine_then_move(tmp_path, monkeypatch):
    monkeypatch.setattr(session_log, "_DIR", str(tmp_path / "logs"))
    world, engine = _ChessWorld(), _Engine()
    reg = WorldRegistry()
    reg._worlds[world.name] = world
    reg.mounted_services = lambda: [engine]
    orch = Orchestrator(reg, SessionStore(root=str(tmp_path / "mem")))
    sess, _ = orch.store.new(world.name, "fake-brain")

    inner = _ScriptLLM()
    llm = session_log.LoggingLLM(inner, "fake-brain")   # 真收口点同款包装 → llm_call 留痕
    with session_log.session_scope(sess.id):
        r = orch.handle(sess, "该你了", llm)

    # 1) 调用去向：引擎收 FEN，世界收走子；各一次、顺序正确
    assert engine.invoked == [("best_move", {"fen": START_FEN})]
    assert world.invoked == [("move", {"from": "e7", "to": "e5"})]
    assert inner.calls == 3 and inner.images_seen == 3, "每步之间都重新看画面"
    assert r["reply"] == "我走了 e7e5，该你了。"

    # 2) 会话历史顺序：user → 引擎调用/结果 → 走子调用/结果 → 最终回复
    msgs = orch.store.get(sess.id).messages
    tool_msgs = [m for m in msgs if m.get("role") == "tool"]
    assert [m["name"] for m in tool_msgs] == ["best_move", "move"]
    assert tool_msgs[0]["content"] == "e7e5", "引擎结果要进历史（下一步 LLM 据此走子）"

    # 3) llm_call 留痕带会话标签，三步齐全，工具调用名可见
    llm_entries = session_log.recent(20, session=sess.id, kinds=("llm_call",))
    assert len(llm_entries) == 3
    assert llm_entries[0]["tool_calls"] == ["best_move"]
    assert llm_entries[1]["tool_calls"] == ["move"]
    assert llm_entries[2]["reply"] == "我走了 e7e5，该你了。"


def test_stream_variant_same_chain(tmp_path, monkeypatch):
    """handle_stream 与 handle 同一套循环：同剧本走流式，事件序里能看到两次工具调用与结果。"""
    monkeypatch.setattr(session_log, "_DIR", str(tmp_path / "logs"))
    world, engine = _ChessWorld(), _Engine()
    reg = WorldRegistry()
    reg._worlds[world.name] = world
    reg.mounted_services = lambda: [engine]
    orch = Orchestrator(reg, SessionStore(root=str(tmp_path / "mem")))
    sess, _ = orch.store.new(world.name, "fake-brain")

    events = list(orch.handle_stream(sess, "该你了", _ScriptLLM()))
    kinds = [e["type"] for e in events]
    calls = [e["name"] for e in events if e["type"] == "tool_call"]
    results = [(e["name"], e["ok"]) for e in events if e["type"] == "tool_result"]
    assert calls == ["best_move", "move"]
    assert results == [("best_move", True), ("move", True)]
    assert kinds[-2:] == ["reply", "done"]
    assert engine.invoked and world.invoked
