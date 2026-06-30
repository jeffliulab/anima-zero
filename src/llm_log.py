"""脑↔大模型流量记账 —— 每一次 LLM 调用都留痕，落到 logs/anima/llm-*.jsonl，供 `anima-logs` 调试页看。

与 `awi_log`（脑↔世界）互补：`/awi` 看脑↔世界，`anima-logs` 看脑↔大模型的详细思考流量。
收口点 = `get_llm()`（大模型唯一构造点）外包一层 `LoggingLLM`——这样主循环、意图分类、解说、对弈陪聊
…所有调用一处全收，记录是顺手的（治"大量思考哪儿都查不到"）。
"""
from __future__ import annotations

import contextvars
import json
import os
import time
from contextlib import contextmanager
from typing import Any

# 一个 session 一个文件：logs/anima/session-<id>.jsonl（无 session 的落 misc-<日期>.jsonl），每行一条 JSON。logs/ 已在 .gitignore。
_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs", "anima")
_SEQ = 0

# 留痕文本的最大留存长度（字符）——只是给写盘一个上界防失控，正常条目都远短于此 = 等同"留全文"。
# 放宽前曾是 system 240 / last_user 400 / reply 600，太短：anima-logs 一键复制/排查时把 system 提示、
# 长回复都截掉了，拿不到"所有信息要素"。现给到几千～两万字级，env 可覆盖（默认集中这一处）。
_MAX_SYSTEM = int(os.getenv("ANIMA_LOG_MAX_SYSTEM", "8000"))
_MAX_USER = int(os.getenv("ANIMA_LOG_MAX_USER", "8000"))
_MAX_REPLY = int(os.getenv("ANIMA_LOG_MAX_REPLY", "20000"))

# 当前 session 标签（请求级上下文变量）：每条日志据此标 session，anima-logs 页可按 session 过滤。
# 后台行为树线程靠 BehaviorRunner.start() 捕获 copy_context() 把它带进线程（否则解说会丢 session）。
_session_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("anima_session", default="")


@contextmanager
def session_scope(session_id: str):
    """在这个 with 块内，所有经 LoggingLLM 的调用都标上 session_id。请求边界处用它包一下即可。"""
    tok = _session_ctx.set(session_id or "")
    try:
        yield
    finally:
        _session_ctx.reset(tok)


def bind_session(session_id: str) -> None:
    """在【当前上下文】里持久设上 session 标签（不像 session_scope 那样退出即 reset）。给 bound_stream 用。"""
    _session_ctx.set(session_id or "")


def bound_stream(session_id: str, gen):
    """把一个同步生成器包成【全程带 session 标签】的生成器（专给 SSE 流式端点用）。

    做法：用一份 copy_context() 先 bind_session，再每步 ctx.run(next, gen) 迭代——这样即便外层
    （Starlette 线程池）每次 next() 复制一份新上下文，生成器体里的 LLM 调用（在多次 yield 之间）也
    始终读得到 session。若像以前那样把 `with session_scope` 写在生成器内部，标签会跨 yield 丢失，
    所有调用落进无归属的 misc 桶（这正是 anima-logs 按会话查永远空的根因）。见 tests/test_anima_logs.py。"""
    ctx = contextvars.copy_context()
    ctx.run(bind_session, session_id)
    while True:
        try:
            yield ctx.run(next, gen)
        except StopIteration:
            return


def current_session() -> str:
    return _session_ctx.get()


def _file_for(session: str) -> str:
    """一个 session 一个文件：logs/anima/session-<id>.jsonl。无 session 的调用（如连通自检）落 misc-<日期>.jsonl。"""
    if session:
        return os.path.join(_DIR, f"session-{session}.jsonl")
    return os.path.join(_DIR, "misc-" + time.strftime("%Y-%m-%d") + ".jsonl")


def _persist(entry: dict) -> None:
    try:
        os.makedirs(_DIR, exist_ok=True)
        with open(_file_for(entry.get("session", "")), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # 落盘失败绝不能影响主流程


def record(model: str, system: str, history: list, tools: list, has_image: bool,
           reply: Any, ms: float, error: str = "") -> None:
    """记一笔脑↔大模型往返。reply 为 LLMReply 或 None（出错时）。token 用量由各 provider 从响应里取（归一 {input,output,total}）。"""
    global _SEQ
    _SEQ += 1
    last_user = next((m.get("text", "") for m in reversed(history or []) if m.get("role") == "user"), "")
    entry = {
        "id": _SEQ,
        "ts": time.strftime("%H:%M:%S"),
        "session": _session_ctx.get(),               # 这次调用属于哪个 session（空=非会话场景，如连通自检）
        "model": model,
        "system": (system or "")[:_MAX_SYSTEM],     # 系统提示（前缀）——据此一眼分辨 主循环/意图分类/解说/陪聊
        "last_user": (last_user or "")[:_MAX_USER],
        "n_history": len(history or []),
        "n_tools": len(tools or []),
        "has_image": bool(has_image),
        "reply": (getattr(reply, "text", "") or "")[:_MAX_REPLY],
        "tool_calls": [tc.name for tc in (getattr(reply, "tool_calls", None) or [])],
        "tokens": getattr(reply, "usage", None),     # {input,output,total} 或 None（provider 没给 / 出错）
        "ms": round(ms, 1),
        "error": error,
    }
    _persist(entry)


def _read_jsonl(path: str) -> list[dict]:
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for ln in f:
                try:
                    out.append(json.loads(ln))
                except Exception:
                    pass
    except Exception:
        pass
    return out


def recent(limit: int = 300, session: str = "") -> list[dict]:
    """读 anima-logs（文件夹为唯一真相，前端经此端点读它）。
    session 非空 → 只读那一盘的 session-<id>.jsonl（一个 session 一个文件）；
    session 为空（全部）→ 合并所有文件、按 id 排序后取末尾 limit 条。"""
    try:
        if not os.path.isdir(_DIR):
            return []
        if session:
            return _read_jsonl(_file_for(session))[-limit:]
        merged: list[dict] = []
        for fn in os.listdir(_DIR):
            if fn.endswith(".jsonl"):
                merged += _read_jsonl(os.path.join(_DIR, fn))
        merged.sort(key=lambda e: e.get("id", 0))
        return merged[-limit:]
    except Exception:
        return []


def sessions() -> list[str]:
    """列出有日志的 session（= session-*.jsonl 文件），按文件最近修改时间倒序（最新的在前）。给 anima-logs 页下拉。"""
    try:
        if not os.path.isdir(_DIR):
            return []
        files = [f for f in os.listdir(_DIR) if f.startswith("session-") and f.endswith(".jsonl")]
        files.sort(key=lambda f: os.path.getmtime(os.path.join(_DIR, f)), reverse=True)
        return [f[len("session-"):-len(".jsonl")] for f in files]
    except Exception:
        return []


class LoggingLLM:
    """包一层记录的 LLM 代理：转发 chat() 给真大脑，顺手把这次调用留痕。实现 LLM 协议（vision/model/chat）。"""

    def __init__(self, inner, name: str) -> None:
        self._inner = inner
        self._name = name
        self.model = getattr(inner, "model", name)
        self.vision = getattr(inner, "vision", False)

    def chat(self, system: str, history: list, tools: list, image_png):
        t0 = time.perf_counter()
        reply = None
        error = ""
        try:
            reply = self._inner.chat(system, history, tools, image_png)
            return reply
        except Exception as e:           # 记下错误再抛出（不吞）
            error = f"{type(e).__name__}: {e}"
            raise
        finally:
            try:
                record(self.model, system, history, tools, image_png is not None, reply,
                       (time.perf_counter() - t0) * 1000, error)
            except Exception:
                pass
