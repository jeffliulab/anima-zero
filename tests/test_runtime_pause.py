"""通用运行时（阶段1）测试：暂停/恢复 + HITL AskHuman（interrupt/checkpoint/resume）。

两部分：
1. AskHuman 叶子逻辑——【手动 tick】确定性验证：提问即挂起、回答到了即消费并恢复。
2. BehaviorRunner 的 paused 循环 + pause/resume/answer——用后台线程 + 有界轮询（不依赖固定 sleep 时长）。

全程零棋种语义：证明这套挂起/求助机制对任意任务的树通用。
"""
from __future__ import annotations

import time

import py_trees
from py_trees.common import Status
from py_trees.composites import Sequence

from anima.behavior import AskHuman, BehaviorRunner, Blackboard


def _wait_until(pred, timeout=2.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.005)
    return False


# ---------- 1) AskHuman 叶子：手动 tick，确定性 ----------
class _SetDone(py_trees.behaviour.Behaviour):
    def __init__(self, bb):
        super().__init__("set_done")
        self.bb = bb

    def update(self):
        self.bb.finished = True
        return Status.SUCCESS


def test_askhuman_poses_then_pauses_then_resumes_on_answer():
    bb = Blackboard(world=None)
    got = []
    ask = AskHuman(bb, "我接管白方可以吗？", options=["可以", "不行"],
                   on_answer=lambda c, a: got.append(a))
    tree = Sequence("seq", memory=False)
    tree.add_children([ask, _SetDone(bb)])

    # 第一拍：提问 → 挂起，后面的节点不该被执行
    tree.tick_once()
    assert bb.pending_question is not None, "应写入待答问题"
    assert bb.pending_question["text"] == "我接管白方可以吗？"
    assert bb.pending_question["options"] == ["可以", "不行"]
    assert bb.paused is True, "提问即挂起（运行时据此停 tick）"
    assert bb.finished is False, "没回答前不该越过 AskHuman 执行后续节点"
    assert any(e["channel"] == "question" for e in bb.events)

    # 还没回答，再 tick 仍挂起（幂等）
    tree.tick_once()
    assert bb.paused is True and bb.finished is False

    # 回答到了 → 消费、清场、解除挂起，树继续往下
    bb.answer = "可以"
    tree.tick_once()
    assert got == ["可以"], "on_answer 应拿到回答"
    assert bb.pending_question is None and bb.answer is None, "回答消费后清场"
    assert bb.paused is False, "回答后解除挂起"
    assert bb.finished is True, "应越过 AskHuman 执行后续节点"
    assert any(e["channel"] == "answer" for e in bb.events)


# ---------- 2) Runner 的 paused 循环 + pause/resume/answer（后台线程） ----------
class _Counter(py_trees.behaviour.Behaviour):
    """每拍自增，永远 RUNNING——用来观测 runner 有没有在 tick。"""
    def __init__(self):
        super().__init__("counter")
        self.n = 0

    def update(self):
        self.n += 1
        return Status.RUNNING


def test_runner_pause_halts_ticking_and_resume_continues():
    bb = Blackboard(world=None)
    counter = _Counter()
    r = BehaviorRunner(bb, counter, tick_s=0.01)
    r.start()
    try:
        assert _wait_until(lambda: counter.n >= 1), "起步应在 tick"
        r.pause()
        assert _wait_until(lambda: r.paused)
        # 暂停后计数应稳定不再增长：连续两次快照相等
        time.sleep(0.05)
        a = counter.n
        time.sleep(0.05)
        b = counter.n
        assert a == b, f"暂停期间不该继续 tick（{a} -> {b}）"
        r.resume()
        assert _wait_until(lambda: counter.n > b), "恢复后应继续 tick"
    finally:
        r.cancel()
        r.join(1.0)


def test_hitl_timeout_predicate():
    # 确定性单测：超时判定（不起线程）
    bb = Blackboard(world=None)
    r = BehaviorRunner(bb, _Counter(), tick_s=1.0)
    assert r._hitl_timed_out() is False, "没有待答问题 → 不超时"
    bb.pending_question = {"id": 1, "text": "?", "options": None, "timeout_s": None, "asked_at": 0.0}
    assert r._hitl_timed_out() is False, "timeout_s=None → 永不超时"
    bb.pending_question = {"id": 1, "text": "?", "options": None, "timeout_s": 0.01,
                           "asked_at": time.monotonic() - 5}
    assert r._hitl_timed_out() is True, "提问已是很久前 → 超时"


def test_runner_hitl_timeout_safe_aborts():
    # 没人回答 + timeout_s 到 → 运行时安全中止本次运行（不无限挂）。embodied 安全的硬需求。
    bb = Blackboard(world=None)
    ask = AskHuman(bb, "我接管白方可以吗？", timeout_s=0.05)
    tree = Sequence("seq", memory=False)
    tree.add_children([ask, _SetDone(bb)])
    r = BehaviorRunner(bb, tree, tick_s=0.01)
    r.start()
    try:
        assert _wait_until(lambda: bb.finished, timeout=2.0), "超时应安全中止"
        assert any(e["channel"] == "end" for e in bb.events), "应 emit 一条安全中止结束事件"
        assert bb.answer is None, "无人回答，不该凭空捏造答案"
    finally:
        r.cancel()
        r.join(1.0)


def test_runner_answer_resumes_and_finishes():
    bb = Blackboard(world=None)
    got = []
    ask = AskHuman(bb, "接管白方？", on_answer=lambda c, a: got.append(a))
    tree = Sequence("seq", memory=False)
    tree.add_children([ask, _SetDone(bb)])
    r = BehaviorRunner(bb, tree, tick_s=0.01)
    r.start()
    try:
        assert _wait_until(lambda: bb.pending_question is not None), "应提问并挂起"
        assert r.paused is True, "等回答期间运行时应处于挂起"
        r.answer("白方")
        r.join(1.0)
        assert bb.finished is True, "回答后应恢复并跑完"
        assert got == ["白方"]
        assert bb.pending_question is None
    finally:
        r.cancel()
        r.join(1.0)
