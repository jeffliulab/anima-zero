"""可复用的"树形积木"——把反复出现的子树结构做成工厂函数，搭新任务的树直接拼。

⛔ 只产**节点拓扑**，零文案、零任务语义（不 import messages/具体任务）——这样它对任何任务通用。
具体任务的判断/文案放各自的叶子（如 trees/boardgame.py 的 DoExit 负责 emit 结束文案）。

py_trees 已有的通用控制流（重试 Retry、超时 Timeout、取反 Inverter、一次性 oneshot…）直接复用，
不在这里重造；这里只放 py_trees 没有的、本项目领域骨架（如"感知-决策-行动"循环）。
"""
from __future__ import annotations

from py_trees.behaviour import Behaviour
from py_trees.composites import Selector, Sequence


def sense_decide_act(perceive: Behaviour, stop_seq: Behaviour,
                     act_seq: Behaviour, wait: Behaviour) -> Behaviour:
    """通用"感知-决策-行动循环"骨架（每拍一次）：

        Sequence「一拍」(memory=False)
        ├─ perceive                      先感知（看一眼环境，更新黑板）
        └─ Selector「据状态决定」(memory=False)
           ├─ stop_seq                   该停就停（满足→收尾退出）
           ├─ act_seq                    轮到我就行动一步
           └─ wait                       否则这拍什么都不做

    memory=False：每拍都从头重新评估守卫条件（不沿用上一拍的 RUNNING 进度），
    这对"每拍重新感知、重新判断该不该停/该不该走"是正确语义。
    """
    root = Sequence("一拍", memory=False)
    decide = Selector("据状态决定", memory=False)
    decide.add_children([stop_seq, act_seq, wait])
    root.add_children([perceive, decide])
    return root
