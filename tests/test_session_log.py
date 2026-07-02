"""Session Logs 统一日志测试（原 test_anima_logs.py 的覆盖整体迁入 + 新信封/转发断言）。

证明：
1. LoggingLLM 留痕→recent() 读回，转发结果不变、出错也记（老覆盖，迁移）；
2. 一个 session 一个文件、按 session 过滤、bound_stream 跨 yield 保标签（老覆盖，迁移）；
3. 公共信封字段齐全（id/t/ts/session/kind），kinds 过滤生效；
4. 合并排序按 (t, id)——进程重启 id 重置也不乱序；
5. awi_log.record 转发进统一日志（带 session 与 kind，service_call 用 server 键）。
"""
from __future__ import annotations

import contextvars

from anima import awi_log, llm_log, session_log
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
    monkeypatch.setattr(session_log, "_DIR", str(tmp_path))
    wrapped = session_log.LoggingLLM(_FakeLLM(LLMReply(text="走 e4")), "fake")
    out = wrapped.chat("你是解说器", [{"role": "user", "text": "解说一下"}], [], None)
    assert out.text == "走 e4", "应原样转发真大脑的回复"
    entries = session_log.recent(10)
    assert entries, "应留痕至少一条"
    last = entries[-1]
    assert last["kind"] == "llm_call"
    assert last["reply"] == "走 e4"
    assert last["last_user"] == "解说一下"
    assert last["model"] == "fake-model"
    assert last["error"] == ""
    # 公共信封字段齐全
    for key in ("id", "t", "ts", "session", "kind"):
        assert key in last, f"信封应含 {key}"


def test_per_session_files_and_recent_filters(tmp_path, monkeypatch):
    monkeypatch.setattr(session_log, "_DIR", str(tmp_path))
    wrapped = session_log.LoggingLLM(_FakeLLM(LLMReply(text="ok")), "fake")
    with session_log.session_scope("sess-A"):
        wrapped.chat("sys", [{"role": "user", "text": "a"}], [], None)
    wrapped.chat("sys", [{"role": "user", "text": "b"}], [], None)   # 这条不在任何 session 里
    assert (tmp_path / "session-sess-A.jsonl").exists(), "每个 session 应单独成一个 session-<id>.jsonl 文件"
    assert not list(tmp_path.glob("session-.jsonl")), "无 session 的调用不该建空名 session 文件"
    only_a = session_log.recent(10, session="sess-A")
    assert len(only_a) == 1 and only_a[0]["last_user"] == "a", "按 session 读只回那一盘的调用"
    assert session_log.sessions() == ["sess-A"], "sessions() 列出有日志的会话（给下拉）"
    assert len(session_log.recent(10)) == 2, "全部=合并所有文件，两条都在"


def test_bound_stream_keeps_session_across_yields(tmp_path, monkeypatch):
    """回归：流式生成器在多次 yield 之间调用 LLM，session 标签必须全程保住。

    复刻真实环境最毒的一点——Starlette 用线程池迭代同步生成器、【每次 next() 都换一份新上下文】。
    旧写法（生成器内部 with session_scope）会跨 yield 丢标签，所有调用落进无归属 misc 桶。"""
    monkeypatch.setattr(session_log, "_DIR", str(tmp_path))
    wrapped = session_log.LoggingLLM(_FakeLLM(LLMReply(text="ok")), "fake")

    def handle_stream():
        yield "start"
        wrapped.chat("sys", [{"role": "user", "text": "step1"}], [], None)
        yield "mid"
        wrapped.chat("sys", [{"role": "user", "text": "step2"}], [], None)
        yield "done"

    # 外层模拟 Starlette：每次 next() 在一份【全新、无 session】的上下文副本里跑
    outer = session_log.bound_stream("sess-S", handle_stream())
    while True:
        fresh = contextvars.copy_context()
        try:
            fresh.run(next, outer)
        except StopIteration:
            break
    tagged = session_log.recent(10, session="sess-S")
    assert len(tagged) == 2, "两次 yield 之间的 LLM 调用都应带 sess-S 标签"
    assert [e["last_user"] for e in tagged] == ["step1", "step2"]


def test_kinds_filter_and_llm_log_shim(tmp_path, monkeypatch):
    """llm_log 兼容层：recent() 只回 kind=llm_call（旧 /api/anima-logs 语义）。"""
    monkeypatch.setattr(session_log, "_DIR", str(tmp_path))
    session_log.record("world_call", {"world": "w", "method": "invoke", "summary": "x", "resp": {}, "ms": 1.0})
    session_log.record_llm("m", "sys", [{"role": "user", "text": "hi"}], [], False, LLMReply(text="ok"), 1.0)
    assert len(session_log.recent(10)) == 2
    assert [e["kind"] for e in session_log.recent(10, kinds=("llm_call",))] == ["llm_call"]
    assert [e["kind"] for e in llm_log.recent(10)] == ["llm_call"], "兼容层只透出 llm_call"


def test_merge_order_survives_seq_reset(tmp_path, monkeypatch):
    """合并排序按 (t, id)：进程重启后 id 从头计（模拟 _SEQ 重置 + 时钟前进），时间在后的仍排在后。"""
    monkeypatch.setattr(session_log, "_DIR", str(tmp_path))
    real_time = session_log.time.time
    monkeypatch.setattr(session_log.time, "time", lambda: real_time() - 60)   # "重启前"：一分钟前
    with session_log.session_scope("sess-1"):
        session_log.record("world_call", {"world": "w", "method": "invoke", "summary": "早", "resp": {}, "ms": 1.0})
    monkeypatch.setattr(session_log, "_SEQ", 0)   # 模拟进程重启：seq 归零
    monkeypatch.setattr(session_log.time, "time", real_time)                 # "重启后"：当前时间
    with session_log.session_scope("sess-2"):
        session_log.record("world_call", {"world": "w", "method": "invoke", "summary": "晚", "resp": {}, "ms": 1.0})
    merged = session_log.recent(10)
    assert [e["summary"] for e in merged] == ["早", "晚"], "id 重置后仍须按时间序（t 兜底）"


def test_awi_record_forwards_with_session_and_kind(tmp_path, monkeypatch):
    monkeypatch.setattr(session_log, "_DIR", str(tmp_path))
    monkeypatch.setattr(awi_log, "_LOG_DIR", str(tmp_path / "awi"))
    with session_log.session_scope("sess-W"):
        awi_log.record("sim-chess", "invoke", "move({'from':'e7','to':'e5'})", 95.2, {"ok": True})
        awi_log.record("chess-engine", "best_move", "best_move → e7e5", 340.0, {"uci": "e7e5"},
                       kind="service_call")
    entries = session_log.recent(10, session="sess-W")
    assert [e["kind"] for e in entries] == ["world_call", "service_call"], "awi 流量应转发进统一日志"
    assert entries[0]["world"] == "sim-chess"
    assert entries[1]["server"] == "chess-engine", "service_call 用 server 键"
    # awi 自己的内存条目也带上了 session（/awi 终端可显示归属）
    assert awi_log.recent(0)[-1]["session"] == "sess-W"
