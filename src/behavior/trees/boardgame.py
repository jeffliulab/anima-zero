"""对弈树 —— 一棵【具体的行为树】（行为树这个抽象层的一个实例），驱动 Chess Mode 的对弈循环。

棋种无关：八个叶子全部通过注入的 `BoardGameAdapter`（棋种工具适配器）干活，换五子棋只换适配器、本文件不动。
走子管线全是确定性代码：perceive 拿画面 → tools.read_board 视觉认局面 → diff_move 认出对手走子 →
engine_move 引擎出手 → world.invoke("move") 发命令看 success/fail → 判终局/退出。
LLM 只在叶子的「解说」介入（注入 narrate 回调；headless 测试用模板）。

树结构（由 idioms.sense_decide_act 组装）：
  Sequence「一拍」
  ├─ Perceive                       每拍先看画面+认局面+认出对手走子
  └─ Selector「据状态决定」
     ├─ Sequence「该停」: ShouldStop → DoExit
     ├─ Sequence「轮到我」: MyTurn → EngineMove → SendMove(失败下拍重试) → Narrate
     └─ WaitTick                    轮到对手/没动 → 这拍什么都不做
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from py_trees.behaviour import Behaviour
from py_trees.common import Status
from py_trees.composites import Sequence

from .. import idioms
from ..blackboard import Blackboard
from ..runner import BehaviorRunner
from ... import config, messages
from ...world_client import RemoteWorld

MAX_FAIL = config.GAME_MAX_FAIL    # send_move 连续失败上限


@dataclass
class BoardGameBlackboard(Blackboard):
    """对弈树的黑板：在通用 Blackboard 之上，补对弈专属字段（belief 局面、执方、棋种适配器…）。"""
    adapter: Any = None                     # BoardGameAdapter（注入的棋种适配器）
    belief: Any = None                      # ANIMA 期望的局面/信念（如 chess.Board），每拍用视觉校准；与世界真值分家
    my_side: str = "white"                  # "white" / "black"
    narrate: Optional[Callable] = None      # (uci, san, state) -> 一句解说
    observed: Optional[dict] = None         # 最近一帧看到的摆放（调试/状态用）
    pending_observed: Optional[dict] = None  # 正在多帧确认的"候选变化"
    observed_streak: int = 0                 # 候选变化连续一致了几帧
    running_streak: int = 0                  # 连续多少拍停在 RUNNING(看不清/确认中)——用于"卡住"报警
    pending_move: Any = None
    pending_san: str = ""
    move_count: int = 0
    resign_streak: int = 0                   # 连续多少拍评分都极差（够久才认输，避免兑子瞬间误判）
    last_uci: str = ""
    last_san: str = ""
    term: dict = field(default_factory=dict)

    def status(self) -> dict:
        side = self.adapter.side_to_move(self.belief)        # 走 tools，不直接碰棋规则(state.turn)
        d = self.base_status()
        d.update({"my_side": self.my_side, "turn": side,
                  "my_turn": side == self.my_side, "move_count": self.move_count})
        return d


# ---------------- 叶子节点 ----------------
class Perceive(Behaviour):
    """每拍：拿画面 → 带置信度地认局面 → （多帧确认后）认出对手走子并推进 state。

    三态语义（这正是"看错了也硬往下走会带歪整盘"的修复）：
    - 看清且局面稳定 → SUCCESS（可以决策）
    - 看不清 / 变化还没连续确认够 → RUNNING（这拍不决策，再看一眼）
    - 世界异常拿不到画面 → FAILURE 且 perceive_fail++（攒到上限会被判 world_unreachable 退出，不再静默空转）
    """

    def __init__(self, bb: BoardGameBlackboard):
        super().__init__("read_board")
        self.bb = bb

    def update(self) -> Status:
        c = self.bb
        # 1) 拿画面 + 角色 meta（世界异常 → 计 perceive_fail；到上限就判 world_unreachable 退出，不再静默空转）
        try:
            obs = c.world.perceive()
        except Exception as e:
            return self._perceive_failed(c, type(e).__name__)
        img = obs.image_png
        state = obs.state or {}
        # 通用：每拍从 controllers 重新认"我执哪方"（不在脑里存死执方）。没有 anima 席位=被换下→如实退出。
        ctrl = state.get("controllers") or {}
        mine = next((s for s in ctrl if ctrl.get(s) == "anima"), None)
        if ctrl and mine is None:
            c.exit_reason = "seat_lost"
            return Status.SUCCESS                        # 本拍进 decide → ShouldStop 据 exit_reason 收尾
        if mine is not None:
            c.my_side = mine
        # 跟着世界 phase 走（phase 是唯一从静态画面看不出来的东西，所以世界要明确声明）：
        #   not_start → 这拍 idle（不驱动世界，等开赛）；game_over → 收尾退出；in_game → 继续往下看。
        phase = state.get("phase")
        if phase == "not_start":
            return Status.RUNNING
        if phase == "game_over" and not c.exit_reason:
            c.exit_reason = "phase:game_over"
            return Status.SUCCESS
        if img is None:
            return self._perceive_failed(c, "无画面")

        # 2) 带置信度地认局面
        placement, uncertain = c.adapter.read_board_detailed(img)
        c.observed = placement
        if uncertain:
            return self._running(c, f"有 {len(uncertain)} 格看不清，再看一眼。")
        c.perceive_fail = 0                              # 拿到并看清了 → 世界异常计数清零

        expected = c.adapter.placement_of(c.belief)
        if placement == expected:                        # 和我的期望一致 → 没有对手新动作，正常决策
            c.pending_observed = None
            c.observed_streak = 0
            c.running_streak = 0
            return Status.SUCCESS

        # 3) 与期望不同 → 可能对手走了。多帧确认这个"变化"连续 N 帧一致才采信（单帧抖动不污染棋局）。
        if placement == c.pending_observed:
            c.observed_streak += 1
        else:
            c.pending_observed = placement
            c.observed_streak = 1
        if c.observed_streak < config.VISION_CONFIRM_FRAMES:
            return self._running(c, None)                # 还没连续确认够 → 再看一拍，先别采信

        # 4) 已连续确认这个变化 → 认出是哪一手（歧义/对不上则跳过、不强行采信、不计致命失败）
        mv = c.adapter.diff_move(c.belief, placement)
        if mv is not None:
            uci = c.adapter.move_uci(mv)
            c.adapter.apply(c.belief, mv)                   # 推进期望局面
            c.emit("opponent", f"对手走 {uci}", uci=uci)
        c.pending_observed = None
        c.observed_streak = 0
        c.running_streak = 0
        return Status.SUCCESS

    def _perceive_failed(self, c, why: str) -> Status:
        c.perceive_fail += 1
        c.emit("fail", f"看不到棋盘（{why}），第 {c.perceive_fail} 次。", cat="perceive")
        if c.perceive_fail > config.GAME_PERCEIVE_MAX_FAIL:
            c.exit_reason = "world_unreachable"          # 让本拍进入 decide → ShouldStop 据 exit_reason 收尾退出
            return Status.SUCCESS
        return Status.FAILURE                            # 还没到上限 → 这拍跳过，下拍再看

    def _running(self, c, msg: Optional[str]) -> Status:
        c.running_streak += 1
        if msg and c.running_streak == 1:                # 首次提示，避免每拍刷屏
            c.emit("vision", msg)
        if c.running_streak == config.GAME_PERCEIVE_MAX_FAIL:   # 长时间无进展 → 可见的"卡住"报警(不静默)
            c.emit("stuck", "视觉长时间看不清/确认不了，可能卡住了——请检查世界/画面。")
        return Status.RUNNING


class ShouldStop(Behaviour):
    """该不该停：用户喊停 / 终局 / 失败超限。"""

    def __init__(self, bb: BoardGameBlackboard):
        super().__init__("该停?")
        self.bb = bb

    def update(self) -> Status:
        c = self.bb
        if c.exit_reason:                               # 已被别处判定要退出（如 Perceive 的 world_unreachable）
            return Status.SUCCESS
        if c.cancelled:
            c.exit_reason = "user_stop"
            return Status.SUCCESS
        term = c.adapter.is_terminal(c.belief)
        if term.get("over"):
            c.exit_reason = "terminal:" + term.get("reason", "")
            c.term = term
            return Status.SUCCESS
        if c.act_fail > MAX_FAIL:
            c.exit_reason = "too_many_fails"
            return Status.SUCCESS
        # 认输：是否该认由【适配器】按棋种判（should_resign，可选——没有就不认），连续够多拍才真认。确认拍数在 config。
        resigner = getattr(c.adapter, "should_resign", None)
        if resigner and resigner(c.belief, c.my_side):
            c.resign_streak += 1
            if c.resign_streak >= config.GAME_RESIGN_CONFIRM:
                c.exit_reason = "resign"
                return Status.SUCCESS
        else:
            c.resign_streak = 0
        return Status.FAILURE


class DoExit(Behaviour):
    def __init__(self, bb: BoardGameBlackboard):
        super().__init__("收尾退出")
        self.bb = bb

    def update(self) -> Status:
        c = self.bb
        if c.exit_reason.startswith("terminal"):
            term = c.term
            winner = term.get("winner")
            c.emit("end", messages.game_end_text(term.get("reason", ""), winner, winner == c.my_side))
        elif c.exit_reason == "user_stop":
            c.emit("end", messages.SKILL_EXIT_REPLY)
        elif c.exit_reason == "seat_lost":
            c.emit("end", messages.GAME_SEAT_LOST_REPLY)
        elif c.exit_reason == "resign":
            # 认输要告诉【世界】（世界是终局的权威）→ 它进 game_over；脑侧只是发起。
            try:
                c.world.invoke("resign")
            except Exception:
                pass
            c.emit("end", messages.GAME_RESIGN_REPLY)
        elif c.exit_reason == "phase:game_over":
            c.emit("end", messages.GAME_OVER_REPLY)
        else:
            c.emit("end", f"对弈中止（{c.exit_reason}）。")
        c.finished = True
        return Status.SUCCESS


class MyTurn(Behaviour):
    """轮到我吗（画面稳定 + 轮次）。仿真里画面恒稳，真机这里加稳定门控。"""

    def __init__(self, bb: BoardGameBlackboard):
        super().__init__("轮到我?")
        self.bb = bb

    def update(self) -> Status:
        c = self.bb
        return Status.SUCCESS if c.adapter.my_turn(c.belief, c.my_side) else Status.FAILURE


class EngineMove(Behaviour):
    """引擎出手（确定性，非 LLM）。"""

    def __init__(self, bb: BoardGameBlackboard):
        super().__init__("engine_move")
        self.bb = bb

    def update(self) -> Status:
        c = self.bb
        mv = c.adapter.engine_move(c.belief)
        if mv is None:
            return Status.FAILURE
        c.pending_move = mv
        c.pending_san = c.adapter.describe(c.belief, mv)   # 须在落子前算 SAN
        return Status.SUCCESS


class SendMove(Behaviour):
    """发命令给世界，看 success/fail。成功推进 state；失败累计、下拍重试。"""

    def __init__(self, bb: BoardGameBlackboard):
        super().__init__("send_move")
        self.bb = bb

    def update(self) -> Status:
        c = self.bb
        if not c.is_writer():
            # 单写者令牌失效（新局已开 / 被接管）→ 不再向同一世界发命令。不计失败（这不是出错）。
            return Status.FAILURE
        mv = c.pending_move
        cmd = c.adapter.to_command(c.belief, mv)
        res = c.world.invoke("move", **cmd)
        if res.ok:
            uci = c.adapter.move_uci(mv)
            c.adapter.apply(c.belief, mv)
            c.act_fail = 0
            c.move_count += 1
            c.last_uci, c.last_san = uci, c.pending_san
            c.pending_move = None
            return Status.SUCCESS
        c.act_fail += 1
        c.emit("fail", f"这手没走成（{res.message}），重看重走。")
        return Status.FAILURE


class Narrate(Behaviour):
    """LLM 解说这一手（唯一的 LLM 介入点；headless 用模板）。"""

    def __init__(self, bb: BoardGameBlackboard):
        super().__init__("解说")
        self.bb = bb

    def update(self) -> Status:
        c = self.bb
        try:
            text = c.narrate(c.last_uci, c.last_san, c.my_side)   # 传 my_side(不是 board)：解说视角直接用执方，且不喂 FEN
        except Exception:
            text = f"我走了 {c.last_san}。"
        c.emit("anima", text, uci=c.last_uci)
        return Status.SUCCESS


class WaitTick(Behaviour):
    """轮到对手 / 画面没动：这拍什么都不做。"""

    def __init__(self, bb: BoardGameBlackboard):
        super().__init__("等一拍")
        self.bb = bb

    def update(self) -> Status:
        return Status.SUCCESS


def build_boardgame_tree(bb: BoardGameBlackboard) -> Behaviour:
    stop_seq = Sequence("该停就停", memory=False)
    stop_seq.add_children([ShouldStop(bb), DoExit(bb)])
    move_seq = Sequence("轮到我就走一手", memory=False)
    move_seq.add_children([MyTurn(bb), EngineMove(bb), SendMove(bb), Narrate(bb)])
    return idioms.sense_decide_act(Perceive(bb), stop_seq, move_seq, WaitTick(bb))


def _template_narrator(uci: str, san: str, my_side: str) -> str:
    return messages.narrate_template(san, uci)


def start_boardgame(shared_world, adapter, my_side: str,
                    narrate: Optional[Callable] = None, display_name: str = "Chess Mode") -> BehaviorRunner:
    """组装一局对弈：黑板 + 对弈树 + 发动机(BehaviorRunner)。返回 runner，调用方 manager.start 后台跑。

    对弈用**自己的短超时世界 client**（不碰共享的长超时 client）：这样协作式取消最多等一个短超时
    就能退出、且 join 不会被旧局的长往返拖住；退出时 teardown 关掉它。
    """
    game_world = RemoteWorld(getattr(shared_world, "name", "world"),
                             getattr(shared_world, "base", ""), timeout=config.GAME_WORLD_TIMEOUT)
    bb = BoardGameBlackboard(
        world=game_world, adapter=adapter, belief=adapter.new_state(),
        my_side=my_side, narrate=narrate or _template_narrator, display_name=display_name,
    )
    side_cn = messages.SIDE_NAMES.get(my_side, my_side)
    bb.emit("start", f"进入 {display_name}，我执{side_cn[0]}。")
    return BehaviorRunner(bb, build_boardgame_tree(bb), teardown=game_world.close)
