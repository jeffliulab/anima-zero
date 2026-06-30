"""RunnerManager 生命周期/单写者测试（P0）：

验证"开新局前先把旧局干净停掉 + 单写者令牌作废旧局"——这正是现状那个 bug 的修复：
旧实现按 session.id 直接覆盖字典项、旧线程没人停还在后台空跑甚至继续 invoke。
"""
from __future__ import annotations

import py_trees

from anima.behavior import BehaviorRunner, Blackboard, RunnerManager


class _NoOp(py_trees.behaviour.Behaviour):
    def update(self):
        return py_trees.common.Status.SUCCESS


def _runner() -> BehaviorRunner:
    bb = Blackboard(world=None)                 # NoOp 不碰 world
    return BehaviorRunner(bb, _NoOp("noop"), tick_s=0.01)


def test_start_stops_old_and_invalidates_its_writer_token():
    m = RunnerManager()
    r1 = _runner()
    m.start("s", r1)
    assert m.active("s")
    e1 = r1.bb.epoch

    r2 = _runner()
    m.start("s", r2)                            # 开新局：应先把 r1 停掉、令牌作废

    assert r1.bb.cancelled is True, "旧 runner 应被取消"
    assert r1.bb.is_writer() is False, "旧 runner 的单写者令牌应失效（不再向世界写）"
    assert r2.bb.is_writer() is True, "新 runner 是当前写者"
    assert r2.bb.epoch > e1, "epoch 应递增"
    assert m.get("s") is r2, "管理员里应是新 runner"

    m.stop("s")
    assert m.get("s") is None, "stop 后应从管理员移除（不残留）"


def test_reap_clears_finished():
    m = RunnerManager()
    r = _runner()
    m.start("k", r)
    r.bb.finished = True                        # 模拟对局自然结束
    r.cancel()
    r.join(1.0)
    m.reap()
    assert m.get("k") is None
