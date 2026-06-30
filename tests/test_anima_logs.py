"""阶段4：anima-logs（脑↔大模型流量收口）测试。

证明：包一层 LoggingLLM 后，每次 chat() 都被留痕到文件夹，recent() 能读回；且转发结果不变、出错也记。
"""
from __future__ import annotations

from anima import llm_log
from anima.llm import LLMReply


class _FakeLLM:
    vision = False
    model = "fake-model"

    def __init__(self, reply=None, boom=False):
        self._reply = reply or LLMReply(text="hi")
        self._boom = boom

    def chat(self, system, history, tools, image_png):
        if self._boom:
            raise RuntimeError("down")
        return self._reply


def test_logging_llm_records_and_recent_reads(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_log, "_DIR", str(tmp_path))
    wrapped = llm_log.LoggingLLM(_FakeLLM(LLMReply(text="走 e4")), "fake")
    out = wrapped.chat("你是解说器", [{"role": "user", "text": "解说一下"}], [], None)
    assert out.text == "走 e4", "应原样转发真大脑的回复"
    entries = llm_log.recent(10)
    assert entries, "应留痕至少一条"
    last = entries[-1]
    assert last["reply"] == "走 e4"
    assert last["last_user"] == "解说一下"
    assert last["model"] == "fake-model"
    assert last["error"] == ""


def test_per_session_files_and_recent_filters(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_log, "_DIR", str(tmp_path))
    wrapped = llm_log.LoggingLLM(_FakeLLM(LLMReply(text="ok")), "fake")
    with llm_log.session_scope("sess-A"):
        wrapped.chat("sys", [{"role": "user", "text": "a"}], [], None)
    wrapped.chat("sys", [{"role": "user", "text": "b"}], [], None)   # 这条不在任何 session 里
    # 一个 session 一个文件
    assert (tmp_path / "session-sess-A.jsonl").exists(), "每个 session 应单独成一个 session-<id>.jsonl 文件"
    assert not list(tmp_path.glob("session-.jsonl")), "无 session 的调用不该建空名 session 文件"
    only_a = llm_log.recent(10, session="sess-A")
    assert len(only_a) == 1 and only_a[0]["last_user"] == "a", "按 session 读只回那一盘的调用"
    assert llm_log.sessions() == ["sess-A"], "sessions() 列出有日志的会话（给下拉）"
    assert len(llm_log.recent(10)) == 2, "全部=合并所有文件，两条都在"


def test_logging_llm_records_errors_and_reraises(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_log, "_DIR", str(tmp_path))
    wrapped = llm_log.LoggingLLM(_FakeLLM(boom=True), "fake")
    raised = False
    try:
        wrapped.chat("sys", [{"role": "user", "text": "x"}], [], None)
    except RuntimeError:
        raised = True
    assert raised, "出错应照常抛出（不吞）"
    last = llm_log.recent(10)[-1]
    assert "RuntimeError" in last["error"] and last["reply"] == ""
