"""HITL —— 通用"向人类提问/求助"叶子（任务无关，任何 skill/世界复用）。

实现 interrupt / checkpoint / resume：运行中的行为树**挂起自己、抛出一个问题、等人回答、带回答从原处恢复**。
一套机制服务多种场景：席位接管确认、视觉歧义确认、真机安全确认……问题文案/选项由调用方注入，本文件零任务语义。

⛔ 不出现任何棋种或具体任务语义——它对任意任务的树通用（与 idioms 同级的通用积木）。
假设：同一时刻只有一个待答问题（提问即挂起整棵树），因此不会有两个 AskHuman 抢同一个 answer。
"""
from __future__ import annotations

import time
from typing import Callable, Optional, Union

from py_trees.behaviour import Behaviour
from py_trees.common import Status

from .blackboard import Blackboard

# 问题文案：可给定值，也可给 callable(bb)->str（需要按当前 belief 动态生成时）
QuestionSpec = Union[str, Callable[[Blackboard], str]]


class AskHuman(Behaviour):
    """提一个问题给人类、挂起树、等回答再恢复。

    一拍语义（每次 update）：
    - 还没问过这题 → 写 pending_question + emit "question" 事件 + 置 paused，返回 RUNNING（运行时据 paused 挂起 tick）。
    - 回答到了（bb.answer 有值）→ 调 on_answer 回填、清场、解除 paused，返回 SUCCESS（树继续）。
    - 已问、还没答 → 保持挂起，返回 RUNNING。

    超时：pending_question 里带 timeout_s/options（供前端展示）和 asked_at（提问时刻，monotonic）。
    **超时由运行时层（BehaviorRunner）看时钟兜底**：挂起超过 timeout_s 没人回 → 安全中止本次运行
    （embodied 安全：断电关节失力，不能让一个没人回的问题无限挂）。timeout_s=None 则永不超时。
    """

    def __init__(self, bb: Blackboard, question: QuestionSpec, *, name: str = "ask_human",
                 options: Optional[list[str]] = None, timeout_s: Optional[float] = None,
                 on_answer: Optional[Callable[[Blackboard, str], None]] = None) -> None:
        super().__init__(name)
        self.bb = bb
        self._question = question
        self._options = options
        self._timeout_s = timeout_s
        self._on_answer = on_answer
        self._qid = 0

    def update(self) -> Status:
        c = self.bb
        # 1) 回答到了 → 消费、清场、恢复
        if c.pending_question is not None and c.answer is not None:
            ans = c.answer
            if self._on_answer is not None:
                self._on_answer(c, ans)
            c.emit("answer", ans)
            c.pending_question = None
            c.answer = None
            c.paused = False
            return Status.SUCCESS
        # 2) 第一次问这题 → 提问 + 挂起
        if c.pending_question is None:
            text = self._question(c) if callable(self._question) else self._question
            self._qid += 1
            c.pending_question = {"id": self._qid, "text": text,
                                  "options": self._options, "timeout_s": self._timeout_s,
                                  "asked_at": time.monotonic()}   # 运行时据此判超时
            c.emit("question", text, options=self._options)
            c.paused = True
            return Status.RUNNING
        # 3) 已问、还没答 → 继续挂起等
        c.paused = True
        return Status.RUNNING
