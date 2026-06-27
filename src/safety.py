"""框架侧安全闸:动作下发给世界之前的一道确定性检查,**不经过 LLM**(5.1 支柱四)。

这一版是薄实现,默认放行(仿真无真机风险)。真机 / 人形版在这里填硬检查:夹爪角度 ≤100°、目标在
标定的安全工作区 / 合法棋盘格内、CAN 是否被占用、不可逆动作前人工审批……

注意(deep-research 修正):安全是**两层、都不经过 LLM**。这里是「框架侧」的慢闸(计划级,适合下棋
这种离散动作);连续控制(人形)还需要**世界侧就近控制器的快确定性盾**(MPC / CBF),那一层住在世界
内部、和快手在一起,框架这边管不到也不该管。
"""
from __future__ import annotations


class SafetyGate:
    """确定性安全闸。`default_allow` 把「放行」变成显式策略,而不是隐式写死。

    - 仿真阶段:`default_allow=True`(无真机风险,放行)。
    - 上真机前:构造时传 `default_allow=False`,在 `check()` 里按世界 / 动作填**确定性硬检查**
      ——夹爪角度 ≤100°、目标在标定的安全工作区 / 合法棋盘格内、CAN 是否被占用、不可逆动作前
      人工审批(HITL)。这些硬检查本次不实现,留到上真机阶段;但把开关显式化,避免换真机时静默裸奔。
    """

    def __init__(self, default_allow: bool = True) -> None:
        self.default_allow = default_allow

    def check(self, world, name: str, args: dict) -> tuple[bool, str]:
        """返回 (放行?, 拦截原因)。真机硬检查在此按世界 / 动作补。"""
        if self.default_allow:
            return True, ""
        return False, "未配置确定性安全规则,默认拒绝(上真机前请实现硬检查)"
