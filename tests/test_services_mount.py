"""service 挂载制测试：world 声明 → registry 惰性连接/缓存 → orchestrator 合并/路由。

界定回顾（见 service_client.py）：world=现实（发命令、过安全闸）；service=顾问（问答、只读、不过闸）。
"""
from __future__ import annotations

from anima import awi_log, session_log
from anima.awi import ActionResult, Capabilities, Observation, ToolSpec
from anima.llm import LLMReply, ToolCall
from anima.orchestrator import Orchestrator
from anima.registry import WorldRegistry
from anima.service_client import RemoteService
from anima.session import SessionStore


class _World:
    """假世界：可配工具与 services 声明。"""
    name = "w"
    base = "fake://w"

    def __init__(self, tools=None, services=None, boom=False):
        self._tools = tools if tools is not None else [ToolSpec("move", "动一下", {}, "tool")]
        self._services = services or []
        self._boom = boom
        self.invoked: list[tuple[str, dict]] = []

    def capabilities(self):
        if self._boom:
            raise RuntimeError("offline")
        return Capabilities(self.name, "t", self._tools, services=self._services)

    def perceive(self):
        return Observation(image_png=None, state={})

    def invoke(self, name, *, _on_progress=None, _should_abort=None, **a):
        # World 协议的客户端旁路参数（进度/取消）：假世界按协议接受并忽略
        self.invoked.append((name, a))
        return ActionResult(True, f"did {name}")


class _Service:
    """假服务：记录调用；capabilities 形状与 RemoteService 一致（kind=read）。"""

    def __init__(self, name="advisor", tools=("best_move",), boom=False):
        self.name = name
        self._tools = [ToolSpec(t, f"顾问工具 {t}", {}, "read") for t in tools]
        self._boom = boom
        self.invoked: list[tuple[str, dict]] = []

    def capabilities(self):
        if self._boom:
            raise RuntimeError("service down")
        return Capabilities(self.name, "s", self._tools)

    def invoke(self, name, **a):
        self.invoked.append((name, a))
        return ActionResult(True, "42", data={"result": 42})


class _SeqLLM:
    vision = False
    model = "fake"

    def __init__(self, replies):
        self._replies = list(replies)
        self._i = 0

    def chat(self, system, history, tools, image):
        self.tools_seen = [t.name for t in tools]
        self.system_seen = system
        r = self._replies[min(self._i, len(self._replies) - 1)]
        self._i += 1
        return r


def _orch(tmp_path, world, services):
    reg = WorldRegistry()
    reg._worlds[world.name] = world
    orch = Orchestrator(reg, SessionStore(root=str(tmp_path)))
    # 挂载来源在 registry.services_for（读 world 声明建真客户端）；orchestrator 层测试用假服务替掉它
    reg.services_for = lambda w: list(services)
    sess, _ = orch.store.new(world.name, "fake")
    return orch, sess


# ---------------- registry 层：world 声明 → 客户端惰性连接/缓存 ----------------

def test_registry_builds_service_clients_from_world_declaration():
    reg = WorldRegistry()
    w = _World(services=[{"name": "chess-engine", "url": "http://localhost:8108"}])
    out = reg.services_for(w)
    assert len(out) == 1 and isinstance(out[0], RemoteService)
    assert out[0].name == "chess-engine" and out[0].mcp_url == "http://localhost:8108/mcp"
    assert reg.services_for(w)[0] is out[0], "同一 URL 复用同一客户端（缓存）"


def test_registry_services_empty_when_world_offline_or_undeclared():
    reg = WorldRegistry()
    assert reg.services_for(_World(services=[])) == []
    assert reg.services_for(_World(boom=True)) == [], "world 离线 → 空清单（惰性，不抛）"
    assert reg.services_for(None) == []


# ---------------- orchestrator 层：合并 / 路由 / 冲突 ----------------

def test_service_tools_merged_and_routed_to_service(tmp_path):
    svc = _Service()
    world = _World()
    orch, sess = _orch(tmp_path, world, [svc])
    llm = _SeqLLM([
        LLMReply(tool_calls=[ToolCall("1", "best_move", {"fen": "xx"})]),
        LLMReply(text="好了"),
    ])
    r = orch.handle(sess, "算一下", llm)
    assert "best_move" in llm.tools_seen and "move" in llm.tools_seen, "服务工具应并进工具单"
    assert svc.invoked == [("best_move", {"fen": "xx"})], "服务工具应路由给服务"
    assert world.invoked == [], "服务工具绝不发给世界"
    assert r["reply"] == "好了"
    assert "顾问工具" in llm.system_seen, "挂了服务应追加 SERVICES_HINT"


def test_name_collision_world_wins(tmp_path):
    svc = _Service(tools=("move",))            # 服务工具与世界工具同名
    world = _World()
    orch, sess = _orch(tmp_path, world, [svc])
    llm = _SeqLLM([
        LLMReply(tool_calls=[ToolCall("1", "move", {"to": "e4"})]),
        LLMReply(text="ok"),
    ])
    orch.handle(sess, "动", llm)
    assert llm.tools_seen.count("move") == 1, "同名只上一份"
    assert world.invoked == [("move", {"to": "e4"})], "同名冲突 world 优先"
    assert svc.invoked == []


def test_service_down_tools_absent_but_loop_survives(tmp_path):
    svc = _Service(boom=True)
    world = _World()
    orch, sess = _orch(tmp_path, world, [svc])
    llm = _SeqLLM([LLMReply(text="聊聊")])
    r = orch.handle(sess, "你好", llm)
    assert "best_move" not in llm.tools_seen, "服务没起 → 它的工具这一轮不上单（诚实呈现）"
    assert r["reply"] == "聊聊"


# ---------------- RemoteService 客户端：记账 kind=service_call ----------------

def test_remote_service_invoke_logs_service_call(tmp_path, monkeypatch):
    monkeypatch.setattr(session_log, "_DIR", str(tmp_path))
    monkeypatch.setattr(awi_log, "_LOG_DIR", str(tmp_path / "awi"))
    svc = RemoteService("advisor", "http://localhost:9")

    # 不联网：把桥换成直接给结果（假 with_session 返回 None 而非协程，免得挂"未 await"警告）
    monkeypatch.setattr("anima.service_client.run_sync", lambda coro, timeout: (True, "e7e5", {"result": "e7e5"}))
    monkeypatch.setattr("anima.service_client.with_session", lambda url, op, t: None)
    with session_log.session_scope("sess-svc"):
        res = svc.invoke("best_move", fen="fake-fen")
    assert res.ok and res.message == "e7e5"
    entries = session_log.recent(10, session="sess-svc")
    assert [e["kind"] for e in entries] == ["service_call"], "服务调用应以 service_call 入统一日志"
    assert entries[0]["server"] == "advisor" and "best_move" in entries[0]["summary"]


def test_remote_service_down_returns_readable_error(monkeypatch, tmp_path):
    monkeypatch.setattr(session_log, "_DIR", str(tmp_path))
    monkeypatch.setattr(awi_log, "_LOG_DIR", str(tmp_path / "awi"))

    def boom(coro, timeout):
        raise ConnectionError("refused")

    monkeypatch.setattr("anima.service_client.run_sync", boom)
    monkeypatch.setattr("anima.service_client.with_session", lambda url, op, t: None)
    res = RemoteService("advisor", "http://localhost:9").invoke("best_move", fen="x")
    assert not res.ok and "没有启动" in res.message, "服务没起 → 可读失败（如实反馈不兜底）"
