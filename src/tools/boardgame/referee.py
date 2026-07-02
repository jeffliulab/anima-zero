"""三方对账裁判（纯逻辑、零 IO）—— v0.5 视觉桥的"不全信任何单只眼"。

对账的三张盘（v1.1 设计：「视觉裁判是一等公民」，裁判归脑）：
  ① 追踪层占用盘 occ_obs（便宜、稳、但盲——只认每格 空/白/黑）
  ② CNN 子型盘 piece_obs（懂子型、但会认错；未启用时传 None → 诚实退化成单层）
  ③ 信念期望占用盘 expected_occ（大脑 belief 的投影——python-chess 持有的逻辑期望）

裁判逻辑（每拍一次）：
  1. 把 ② 塌成占用盘，与 ① 逐格互检——两只独立的眼不一致 → CONFLICT（谁都不信，再看一眼）；
  2. 任一层自报看不清的格 → UNCERTAIN（不硬猜）；
  3. 两眼一致且都看清：与期望 ③ 相同 → STEADY（对手没动）；不同 → CANDIDATE（占用盘交
     diff_move 认走子，走既有多帧确认——本模块不碰行为树，只给结论）。

铁律：绝不静默走错——冲突/看不清一律不推进信念，交上层"再看一眼"。
这里不 import 棋规/行为树/识别器——纯函数好单测，也保证"多眼融合"职责不塞进适配器。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# 裁判三态 + 冲突（对弈树把 CONFLICT/UNCERTAIN 都当"再看一眼"，note 不同便于诊断）
STEADY = "steady"          # 两眼一致 & 与期望一致：对手没动，可正常决策
CANDIDATE = "candidate"    # 两眼一致 & 与期望不同：疑似对手走子，交 diff_move + 多帧确认
CONFLICT = "conflict"      # 两只眼互相矛盾：谁都不信，再看一眼
UNCERTAIN = "uncertain"    # 有格子看不清：不硬猜，再看一眼


@dataclass
class Verdict:
    status: str
    observed_for_diff: Optional[dict] = None      # CANDIDATE 时：交给 diff_move 的占用盘
    uncertain_squares: set = field(default_factory=set)
    disagree_squares: set = field(default_factory=set)
    note: str = ""


def collapse_to_occ(piece_board: dict) -> dict:
    """子型盘 {sq:'P'/'n'} → 占用盘 {sq:'w'|'b'}（大写=白、小写=黑；空格不出现）。"""
    return {sq: ("w" if str(sym).isupper() else "b") for sq, sym in piece_board.items()}


def judge(occ_obs: dict, occ_uncertain: set,
          piece_obs: Optional[dict], piece_uncertain: set,
          expected_occ: dict) -> Verdict:
    """三方对账（见模块 docstring）。piece_obs=None 表示 CNN 层未启用 → 单层（占用 vs 期望）。"""
    uncertain = set(occ_uncertain or ()) | set(piece_uncertain or ())

    # 1) 两眼互检（双保险核心）：CNN 子型盘塌到占用空间，与追踪层逐格比。
    #    已被任一层标"看不清"的格不算冲突（它走 UNCERTAIN 路径，不冤枉哪只眼）。
    disagree: set = set()
    if piece_obs is not None:
        cnn_occ = collapse_to_occ(piece_obs)
        keys = set(occ_obs) | set(cnn_occ)
        disagree = {sq for sq in keys if occ_obs.get(sq) != cnn_occ.get(sq)} - uncertain
    if disagree:
        return Verdict(CONFLICT, disagree_squares=disagree,
                       note=f"两只眼在 {len(disagree)} 格不一致，谁都不信，再看一眼")

    # 2) 有格子看不清 → 不硬猜。
    if uncertain:
        return Verdict(UNCERTAIN, uncertain_squares=uncertain,
                       note=f"{len(uncertain)} 格看不清，再看一眼")

    # 3) 两眼一致且都看清：和期望比。
    if occ_obs == expected_occ:
        return Verdict(STEADY, note="与期望一致（对手没动）")
    return Verdict(CANDIDATE, observed_for_diff=dict(occ_obs),
                   note="占用有变化，交 diff_move 认走子（多帧确认后采信）")
