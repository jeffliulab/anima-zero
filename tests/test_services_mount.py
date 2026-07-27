"""service 挂载制测试：Host 组装（config.services()）→ registry 建/缓存客户端 → orchestrator 合并/路由。

界定回顾（见 service_client.py）：world=现实（发命令、过安全闸）；service=顾问（问答、只读、不过闸）。
挂载来源=大脑自己的配置（标准 MCP：连哪些 server 是 Host 的活，server 之间互不相识、world 不声明服务）。
"""
from __future__ import annotations

from anima import awi_log, session_log
from anima.core.awi import ActionResult, Capabilities, Observation, ToolSpec
from anima.llm import LLMReply, ToolCall
from anima.core.orchestrator import Orchestrator
from anima.clients.registry import WorldRegistry
from anima.clients.service_client import RemoteService
from anima.session import SessionStore


class _World:
    """假世界：可配工具。"""
    name = "w"
    base = "fake://w"

    def __init__(self, tools=None, boom=False):
        self._tools = tools if tools is not None else [ToolSpec("move", "动一下", {}, "tool")]
        self._boom = boom
        self.invoked: list[tuple[str, dict]] = []

    def capabilities(self):
        if self._boom:
            raise RuntimeError("offline")
        return Capabilities(self.name, "t", self._tools)

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
    # 挂载来源在 registry.mounted_services（读 config.services() 建真客户端）；orchestrator 层测试用假服务替掉它
    reg.mounted_services = lambda: list(services)
    sess, _ = orch.store.new(world.name, "fake")
    return orch, sess


# ---------------- registry 层：config.services()（Host 组装）→ 客户端惰性建/缓存 ----------------

def test_registry_builds_service_clients_from_host_config(monkeypatch):
    monkeypatch.setenv("ANIMA_SERVICES", "boardgame-engine=http://localhost:8108")
    reg = WorldRegistry()
    out = reg.mounted_services()
    assert len(out) == 1 and isinstance(out[0], RemoteService)
    assert out[0].name == "boardgame-engine" and out[0].mcp_url == "http://localhost:8108/mcp"
    assert reg.mounted_services()[0] is out[0], "同一 URL 复用同一客户端（缓存）"


def test_registry_default_mounts_boardgame_engine(monkeypatch):
    """没设 ANIMA_SERVICES → 默认清单必含 boardgame-engine（T0：加服务=追加，绝不替换默认）。"""
    monkeypatch.delenv("ANIMA_SERVICES", raising=False)
    monkeypatch.delenv("ANIMA_BOARDGAME_ENGINE_URL", raising=False)
    out = WorldRegistry().mounted_services()
    assert [s.name for s in out] == ["boardgame-engine"]
    assert out[0].mcp_url == "http://localhost:8108/mcp"


def test_registry_services_empty_when_config_empty(monkeypatch):
    """显式配空（如部署时不带任何顾问）→ 空清单，不抛。"""
    monkeypatch.setenv("ANIMA_SERVICES", "none")   # 只有非法项 → 解析结果为空
    assert WorldRegistry().mounted_services() == []


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
    assert "Advisory tools" in llm.system_seen, "挂了服务应追加 SERVICES_HINT"


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
    monkeypatch.setattr("anima.clients.service_client.run_sync", lambda coro, timeout: (True, "e7e5", {"result": "e7e5"}))
    monkeypatch.setattr("anima.clients.service_client.with_session", lambda url, op, t: None)
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

    monkeypatch.setattr("anima.clients.service_client.run_sync", boom)
    monkeypatch.setattr("anima.clients.service_client.with_session", lambda url, op, t: None)
    res = RemoteService("advisor", "http://localhost:9").invoke("best_move", fen="x")
    assert not res.ok, "服务没起 → 必须如实报失败，不许兜底"
    # 断言的是**实质**：错误必须指向"它可能没起来"这个可行动的原因，而不是某一句措辞。
    assert "not be running" in res.message, "失败原因要说到点子上，人才知道该去起服务"
