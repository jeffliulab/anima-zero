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


def test_bound_stream_keeps_session_across_yields(tmp_path, monkeypatch):
    """回归：流式生成器在多次 yield 之间调用 LLM，session 标签必须全程保住。

    复刻真实环境最毒的一点——Starlette 用线程池迭代同步生成器、【每次 next() 都换一份新上下文】。
    旧写法（生成器内部 with session_scope）会跨 yield 丢标签，所有调用落进无归属 misc 桶
    （= anima-logs 按会话查永远空的根因）。bound_stream 必须扛住它。"""
    import contextvars

    monkeypatch.setattr(llm_log, "_DIR", str(tmp_path))
    wrapped = llm_log.LoggingLLM(_FakeLLM(LLMReply(text="ok")), "fake")

    def handle_stream():
        # 模拟主循环：在多次 yield 之间真正调用 LLM（每次调用经 LoggingLLM 落一条日志）
        yield "start"
        wrapped.chat("sys", [{"role": "user", "text": "step1"}], [], None)
        yield "mid"
        wrapped.chat("sys", [{"role": "user", "text": "step2"}], [], None)
        yield "done"

    # 外层模拟 Starlette：每次 next() 在一份【全新、无 session】的上下文副本里跑
    outer = llm_log.bound_stream("sess-S", handle_stream())
    while True:
        fresh = contextvars.copy_context()
        try:
            fresh.run(next, outer)
        except StopIteration:
            break

    # 两次 LLM 调用都应归到 sess-S（而不是落进 misc）
    only_s = llm_log.recent(10, session="sess-S")
    assert [e["last_user"] for e in only_s] == ["step1", "step2"], "跨 yield 的每次调用都应带上 session"
    assert (tmp_path / "session-sess-S.jsonl").exists(), "应写进 session-<id>.jsonl，而非 misc"


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
