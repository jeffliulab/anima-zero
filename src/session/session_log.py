"""按会话统一日志（Session Logs）—— 大脑一切对外行为的**单一真相**。

一个会话一个文件 `logs/sessions/session-<id>.jsonl`，每行一条 JSON，公共信封：
    {"id": 17, "t": 1751421824.3, "ts": "12:03:44", "session": "s_...", "kind": "...", ...payload}

kind 三种（payload 各自不同）：
- llm_call     脑↔大模型：model/system/last_user/reply/tool_calls/tokens/ms/error
- world_call   脑↔世界（MCP）：world/method(capabilities|perceive|invoke|progress)/summary/resp/ms
- service_call 脑↔挂载服务（如象棋引擎）：server/method/summary/resp/ms

设计决定（改动前先读）：
- **单一真相 = 本目录**；`logs/awi-*.jsonl` 日文件是 /awi 仪表盘与 eval 的投影（awi_log 双写转发到这里），
  `logs/anima/` 是旧系统留盘归档（已停写）。
- 前端传感区每秒轮询的 /api/perceive **不入账**：那是展示层流量，入账会以每秒一条淹没正文；
  只有聊天请求上下文里的 perceive/invoke 会入账——这正是「ANIMA 看到了什么、随后做了什么」的语义。
- 信封带 `t`（unix 秒）：合并排序按 (t, id)——进程重启后 id 从头计，单靠 id 排序会乱，t 兜住。
- 会话标签靠 contextvars 请求级上下文（session_scope / bound_stream），LLM、世界、服务三路共用同一标签。
"""
from __future__ import annotations

import contextvars
import json
import os
import time
from contextlib import contextmanager
from typing import Any, Iterable

from .. import config, paths

# 一个 session 一个文件：logs/sessions/session-<id>.jsonl（无 session 的落 misc-<日期>.jsonl）。logs/ 已在 .gitignore。
_DIR = os.path.join(paths.LOGS_DIR, "sessions")
_SEQ = 0

# 当前 session 标签（请求级上下文变量）：每条日志据此标 session，Session Logs 页可按 session 过滤。
_session_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("anima_session", default="")


@contextmanager
def session_scope(session_id: str):
    """在这个 with 块内，所有留痕（LLM/世界/服务）都标上 session_id。请求边界处用它包一下即可。"""
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
    （Starlette 线程池）每次 next() 复制一份新上下文，生成器体里的调用（在多次 yield 之间）也
    始终读得到 session。若像早期那样把 `with session_scope` 写在生成器内部，标签会跨 yield 丢失，
    所有调用落进无归属的 misc 桶（= 按会话查永远空的根因）。见 tests/test_session_log.py。"""
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


def record(kind: str, payload: dict) -> None:
    """记一笔（任意 kind）：补公共信封（id/t/ts/session/kind）后落盘。payload 不被修改。"""
    global _SEQ
    _SEQ += 1
    entry = {
        "id": _SEQ,
        "t": round(time.time(), 3),
        "ts": time.strftime("%H:%M:%S"),
        "session": _session_ctx.get(),
        "kind": kind,
    }
    entry.update(payload)
    _persist(entry)


def record_llm(model: str, system: str, history: list, tools: list, has_image: bool,
               reply: Any, ms: float, error: str = "") -> None:
    """记一笔脑↔大模型往返（kind=llm_call）。reply 为 LLMReply 或 None（出错时）。"""
    last_user = next((m.get("text", "") for m in reversed(history or []) if m.get("role") == "user"), "")
    record("llm_call", {
        "model": model,
        "system": (system or "")[:config.LOG_MAX_SYSTEM],
        "last_user": (last_user or "")[:config.LOG_MAX_USER],
        "n_history": len(history or []),
        "n_tools": len(tools or []),
        "has_image": bool(has_image),
        "reply": (getattr(reply, "text", "") or "")[:config.LOG_MAX_REPLY],
        "tool_calls": [tc.name for tc in (getattr(reply, "tool_calls", None) or [])],
        "tokens": getattr(reply, "usage", None),   # {input,output,total} 或 None（provider 没给 / 出错）
        "ms": round(ms, 1),
        "error": error,
    })


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


def recent(limit: int = 300, session: str = "", kinds: Iterable[str] | None = None) -> list[dict]:
    """读 Session Logs（文件夹为唯一真相，前端经端点读它）。
    session 非空 → 只读那一盘的 session-<id>.jsonl；为空 → 合并所有文件。
    合并排序按 (t, id)（跨进程重启仍有序）；kinds 非空 → 只留这些 kind。"""
    try:
        if not os.path.isdir(_DIR):
            return []
        if session:
            entries = _read_jsonl(_file_for(session))
        else:
            entries = []
            for fn in os.listdir(_DIR):
                if fn.endswith(".jsonl"):
                    entries += _read_jsonl(os.path.join(_DIR, fn))
        if kinds is not None:
            allowed = set(kinds)
            entries = [e for e in entries if e.get("kind") in allowed]
        entries.sort(key=lambda e: (e.get("t", 0.0), e.get("id", 0)))
        return entries[-limit:]
    except Exception:
        return []


def sessions() -> list[str]:
    """列出有日志的 session（= session-*.jsonl 文件），按文件最近修改时间倒序（最新在前）。给下拉用。"""
    try:
        if not os.path.isdir(_DIR):
            return []
        files = [f for f in os.listdir(_DIR) if f.startswith("session-") and f.endswith(".jsonl")]
        files.sort(key=lambda f: os.path.getmtime(os.path.join(_DIR, f)), reverse=True)
        return [f[len("session-"):-len(".jsonl")] for f in files]
    except Exception:
        return []


class LoggingLLM:
    """包一层记录的 LLM 代理：转发 chat() 给真大脑，顺手留痕（kind=llm_call）。实现 LLM 协议（vision/model/chat）。
    收口点 = get_llm()（大模型唯一构造点）——所有 LLM 调用一处全收。"""

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
                record_llm(self.model, system, history, tools, image_png is not None, reply,
                           (time.perf_counter() - t0) * 1000, error)
            except Exception:
                pass
