"""开发自测接口测试：/api/dev/turn 的门控（默认关）与"回复+本轮流水"返回形状。"""
from __future__ import annotations

from fastapi.testclient import TestClient

from anima import config, session_log
from anima.llm import LLMReply


class _FakeLLM:
    vision = False
    model = "fake"

    def chat(self, system, history, tools, image_png):
        return LLMReply(text="在的")


def _client(monkeypatch, tmp_path, dev_on: bool):
    import anima.presentation.server as srv
    from anima.core.orchestrator import Orchestrator
    from anima.session import SessionStore

    monkeypatch.setattr(config, "DEV_API", dev_on)
    monkeypatch.setattr(session_log, "_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(srv, "get_llm", lambda name: session_log.LoggingLLM(_FakeLLM(), "fake"))
    # 会话store换临时目录（绝不污染真实 memory/sessions），编排器跟着换
    store = SessionStore(root=str(tmp_path / "mem"))
    monkeypatch.setattr(srv, "store", store)
    monkeypatch.setattr(srv, "orchestrator", Orchestrator(srv.registry, store))
    return TestClient(srv.app)


def test_dev_turn_disabled_by_default(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path, dev_on=False)
    r = c.post("/api/dev/turn", json={"message": "hi"}).json()
    assert "error" in r and "ANIMA_DEV_API" in r["error"], "默认关闭并告知怎么开"


def test_dev_turn_returns_reply_and_turn_log(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path, dev_on=True)
    r = c.post("/api/dev/turn", json={"message": "你好", "world": None}).json()
    assert r["reply"] == "在的"
    assert r["session_id"].startswith("s_")
    kinds = [e["kind"] for e in r["log"]]
    assert "llm_call" in kinds, "本轮流水应含 llm_call（纯聊天无世界/服务调用）"
    # 同一会话续一轮：只返回新增的流水（不是全量历史）
    r2 = c.post("/api/dev/turn", json={"message": "再来", "session_id": r["session_id"]}).json()
    assert r2["session_id"] == r["session_id"]
    assert len(r2["log"]) >= 1
    first_ids = {e["id"] for e in r["log"]}
    assert all(e["id"] not in first_ids for e in r2["log"]), "续轮只回本轮新增流水"
