"""框架侧安全闸:动作下发给世界之前的一道确定性检查,**不经过 LLM**(5.1 支柱四)。

这一版是薄实现,默认放行(仿真无真机风险)。真机 / 人形版在这里填硬检查:夹爪角度 ≤100°、目标在
标定的安全工作区 / 合法棋盘格内、CAN 是否被占用、不可逆动作前人工审批……

注意(deep-research 修正):安全是**两层、都不经过 LLM**。这里是「框架侧」的慢闸(计划级,适合下棋
这种离散动作);连续控制(人形)还需要**世界侧就近控制器的快确定性盾**(MPC / CBF),那一层住在世界
内部、和快手在一起,框架这边管不到也不该管。
"""
from __future__ import annotations

from .. import prompts
from .awi import NON_MUTATING_KINDS


class SafetyGate:
    """确定性安全闸。`default_allow` 把「放行」变成显式策略,而不是隐式写死。

    - 仿真阶段:`default_allow=True`(无真机风险,放行)。
    - 上真机前:构造时传 `default_allow=False`,在 `check()` 里按世界 / 动作填**确定性硬检查**
      ——夹爪角度 ≤100°、目标在标定的安全工作区 / 合法棋盘格内、CAN 是否被占用、不可逆动作前
      人工审批(HITL)。这些硬检查本次不实现,留到上真机阶段;但把开关显式化,避免换真机时静默裸奔。
    """

    def __init__(self, default_allow: bool = True,
                 needs_approval: tuple[str, ...] = (), blocked: tuple[str, ...] = ()) -> None:
        self.default_allow = default_allow
        self._needs_approval = set(needs_approval)   # 这些动作执行前需人工批准（不可逆/高风险）
        self._blocked = set(blocked)                 # 这些动作确定性硬拦（永不放行）

    # 三档决策：'allow'(放行) / 'approve'(需人批) / 'deny'(硬拦)。真机硬检查（夹爪角度≤100°、目标在
    # 标定工作区/合法棋盘格、CAN 是否被占用）按动作在此补；当前仿真阶段按集合 + default_allow 分档。
    def decide(self, world, name: str, args: dict, declared_kind: str = "tool") -> str:
        """⛔ `declared_kind` 是**世界自己说**这个动作改不改变世界（AWI 的 kind / MCP 的
        readOnlyHint）。它是**输入，不是授权**——本方法可以参考它，但绝不能因为它而不被调用。

        这条边界是有原因的：编排器过去按 kind 决定"要不要过闸"，等于把闸门开关交给了远端。
        现在编排器对每个世界动作都调本方法，判断权完整地留在这里（= 操作者的策略）。
        改回去等于把红线还给世界，别改。

        当前策略：非改动类（read/judge）在仿真阶段放行——与历史行为一致，所以今天的行为零变化；
        变的只是**谁在做这个判断**。上真机时在这里按 world/name/args 填确定性硬检查，
        并且**不要**信 declared_kind 就免检。
        """
        if name in self._blocked:
            return "deny"
        if name in self._needs_approval:
            return "approve"
        if declared_kind in NON_MUTATING_KINDS:
            return "allow"
        return "allow" if self.default_allow else "deny"

    def check(self, world, name: str, args: dict, declared_kind: str = "tool") -> tuple[bool, str]:
        """主循环用的二元闸（向后兼容）：返回 (放行?, 拦截原因)。
        'approve' 档在当前【同步】主循环里先拦下并说明——真机阶段再补"挂起→人工批准→放行"的 HITL 放行流程
        （那时复用 AskHuman 那套 interrupt/resume，不在仿真阶段假装已实现）。"""
        d = self.decide(world, name, args, declared_kind)
        if d == "allow":
            return True, ""
        if d == "approve":
            return False, prompts.SAFETY_NEEDS_APPROVAL
        return False, (prompts.SAFETY_RULE_MATCHED if name in self._blocked
                       else prompts.SAFETY_NO_RULES)
