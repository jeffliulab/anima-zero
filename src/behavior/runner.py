"""BehaviorRunner —— 行为树的"发动机"：让一棵静止的树在后台每拍 tick，直到结束。

薄薄一层：内核直接用 py_trees 的 `BehaviourTree`（复用它的 setup/tick/shutdown），自己只补
"后台线程 + 每拍周期 + 可取消 + 异常兜底 + 退出清理"这层 py_trees 不直接给的东西。
**不重写树遍历**——只调 `BehaviourTree.tick()`。

并发模型 = threading（不是 asyncio）：对'每秒一拍'这点负载够用、且与现有纯同步栈一致。
取消是协作式的（置 `_stop` + cancelled），最多一拍内生效；叶子里的世界 IO 用**短超时** client，
所以即便正卡在一次世界往返里，也最多等那个短超时就能退出（见 trees/boardgame.start_*）。
"""
from __future__ import annotations

import contextvars
import threading
import time
from typing import Any, Callable, Optional

import py_trees
from py_trees.behaviour import Behaviour

from .. import config, messages
from .blackboard import Blackboard


class BehaviorRunner:
    def __init__(self, bb: Blackboard, tree: Behaviour, *,
                 tick_s: float = config.GAME_TICK_S, teardown: Optional[Callable[[], Any]] = None):
        self.bb = bb
        self.tree = py_trees.trees.BehaviourTree(tree)   # 复用 py_trees 运行器内核
        self._tick_s = tick_s
        self._teardown = teardown                        # 退出时清理（如关短超时 client）；注入，避免通用层 import 具体
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self.tree.setup()                                # 复用 py_trees
        # 捕获当前上下文（含 llm_log 的 session 标签）让后台线程继承——否则线程里的解说 LLM 调用会丢 session。
        ctx = contextvars.copy_context()
        self._thread = threading.Thread(target=lambda: ctx.run(self._run), daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            while not self.bb.finished and not self._stop.is_set():
                if self.bb.paused:                       # 暂停/等人回答时挂起：不 tick、不驱动世界，线程仍活着
                    if self._hitl_timed_out():           # 但若是 AskHuman 在等、且超了 timeout_s → 安全中止（不无限挂）
                        self.bb.emit("end", messages.HITL_TIMEOUT_REPLY)
                        self.bb.finished = True
                        break
                else:
                    try:
                        self.tree.tick()                 # 复用 py_trees 单拍（纯决策，快速返回）
                    except Exception as e:
                        self.bb.emit("error", f"行为树一拍出错：{type(e).__name__}: {e}")
                if self.bb.finished:
                    break
                self._stop.wait(self._tick_s)            # 可被 cancel 提前唤醒 → 取消/恢复延迟 ≤ 一拍
        finally:
            try:
                self.tree.shutdown()
            finally:
                if self._teardown:
                    self._teardown()

    def _hitl_timed_out(self) -> bool:
        """挂起且有 AskHuman 待答问题、且超过其 timeout_s → True（timeout_s=None 永不超时）。"""
        q = self.bb.pending_question
        if not q:
            return False
        timeout_s, asked_at = q.get("timeout_s"), q.get("asked_at")
        return bool(timeout_s and asked_at is not None and (time.monotonic() - asked_at) > timeout_s)

    def cancel(self) -> None:
        self._stop.set()
        self.bb.cancelled = True

    # ---- 暂停 / 恢复 / 回答（通用运行时能力，任务无关；对标 ROS Action 的可抢占）----
    def pause(self) -> None:
        """挂起：停止 tick（世界不再被驱动），线程保活。恢复后从当前 belief 继续。"""
        self.bb.paused = True

    def resume(self) -> None:
        """恢复：解除挂起，下一拍(≤tick_s)继续 tick。"""
        self.bb.paused = False

    def answer(self, text: str) -> None:
        """回填人类对 AskHuman 问题的回答并解除挂起：下一拍 AskHuman 消费它、树继续。"""
        self.bb.answer = text
        self.bb.paused = False

    @property
    def paused(self) -> bool:
        return self.bb.paused

    def join(self, timeout: float | None = None) -> None:
        if self._thread:
            self._thread.join(timeout)

    @property
    def finished(self) -> bool:
        return self.bb.finished

    def status(self) -> dict:
        return self.bb.status()

    def events_since(self, last_id: int) -> list:
        return self.bb.events_since(last_id)
