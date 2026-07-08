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

    def __init__(self, default_allow: bool = True,
                 needs_approval: tuple[str, ...] = (), blocked: tuple[str, ...] = ()) -> None:
        self.default_allow = default_allow
        self._needs_approval = set(needs_approval)   # 这些动作执行前需人工批准（不可逆/高风险）
        self._blocked = set(blocked)                 # 这些动作确定性硬拦（永不放行）

    # 三档决策：'allow'(放行) / 'approve'(需人批) / 'deny'(硬拦)。真机硬检查（夹爪角度≤100°、目标在
    # 标定工作区/合法棋盘格、CAN 是否被占用）按动作在此补；当前仿真阶段按集合 + default_allow 分档。
    def decide(self, world, name: str, args: dict) -> str:
        if name in self._blocked:
            return "deny"
        if name in self._needs_approval:
            return "approve"
        return "allow" if self.default_allow else "deny"

    def check(self, world, name: str, args: dict) -> tuple[bool, str]:
        """主循环用的二元闸（向后兼容）：返回 (放行?, 拦截原因)。
        'approve' 档在当前【同步】主循环里先拦下并说明——真机阶段再补"挂起→人工批准→放行"的 HITL 放行流程
        （那时复用 AskHuman 那套 interrupt/resume，不在仿真阶段假装已实现）。"""
        d = self.decide(world, name, args)
        if d == "allow":
            return True, ""
        if d == "approve":
            return False, "这是高风险/不可逆动作，需人工批准后才能执行（真机阶段接 HITL 放行）"
        return False, ("命中确定性安全规则，已拦截" if name in self._blocked
                       else "未配置确定性安全规则，默认拒绝(上真机前请实现硬检查)")
