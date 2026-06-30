"""对弈行为树冒烟测试：用一个内存假世界（不起 HTTP），确定性地逐拍 tick 行为树，
验证整条对弈回路——看盘(视觉)→引擎出手→发命令→认出对手走子→终局——都真的跑通。

故意【手动 tick】（不经 BehaviorRunner 的后台线程/sleep），让测试快、可复现、不依赖时间。
这是大重构"行为不变"的对照基线之一。
"""
from __future__ import annotations

import chess

import render  # world/sim-chess/render.py（conftest 加进 sys.path）
from anima import config
from anima.awi import ActionResult, Capabilities, Observation, ToolSpec
from anima.behavior.trees import boardgame
from anima.tools.boardgame.chess import ChessAdapter


class FakeWorld:
    """内存版 sim-chess：perceive 返回当前棋盘的渲染图；invoke('move') 把合法着法走到内部棋盘。

    只回 {ok, message}，绝不给大脑结构化真值——和真世界的通信契约一致。
    """

    def __init__(self, board: chess.Board | None = None):
        self.name = "fake-chess"
        self.base = "fake://chess"
        self.board = board or chess.Board()

    def perceive(self) -> Observation:
        return Observation(image_png=render.to_png(render.render_board(self.board)), state={})

    def invoke(self, name: str, **cmd) -> ActionResult:
        if name != "move":
            return ActionResult(ok=False, message=f"未知命令 {name}")
        uci = f"{cmd['from']}{cmd['to']}{cmd.get('promotion', '')}"
        try:
            mv = chess.Move.from_uci(uci)
        except ValueError:
            return ActionResult(ok=False, message=f"坐标解析失败 {uci}")
        if mv not in self.board.legal_moves:
            return ActionResult(ok=False, message="非法着法")
        self.board.push(mv)
        return ActionResult(ok=True, message="ok")

    def capabilities(self) -> Capabilities:
        return Capabilities(name=self.name, version="test",
                            tools=[ToolSpec("move", "落子", {}, "tool")])


def _bb(world: FakeWorld, belief: chess.Board, my_side="white") -> boardgame.BoardGameBlackboard:
    return boardgame.BoardGameBlackboard(
        world=world, adapter=ChessAdapter(), belief=belief, my_side=my_side,
        narrate=lambda uci, san, st: f"走了 {san}", display_name="Chess Mode",
    )


def _channels(bb):
    return [e["channel"] for e in bb.events]


def test_anima_makes_a_move_from_startpos():
    world = FakeWorld()
    bb = _bb(world, ChessAdapter().new_state(), my_side="white")
    tree = boardgame.build_boardgame_tree(bb)

    tree.tick_once()

    assert bb.move_count == 1, "ANIMA(白) 应在第一拍走一手"
    assert world.board.fullmove_number >= 1 and world.board.turn == chess.BLACK, "世界棋盘应已落子、轮到黑"
    assert "anima" in _channels(bb), "应 emit 一条 anima 解说事件"
    assert bb.act_fail == 0


def test_opponent_move_is_detected_by_vision():
    world = FakeWorld()
    bb = _bb(world, ChessAdapter().new_state(), my_side="white")
    tree = boardgame.build_boardgame_tree(bb)

    tree.tick_once()                 # ANIMA(白) 走一手，轮到黑
    # 模拟对手(黑)走一手：直接在世界棋盘上落子（不经 ANIMA）
    black_reply = next(iter(world.board.legal_moves))
    world.board.push(black_reply)

    # 多帧确认：候选"变化"要连续 VISION_CONFIRM_FRAMES 帧一致才采信（单帧抖动不算）
    for _ in range(config.VISION_CONFIRM_FRAMES):
        tree.tick_once()
    assert "opponent" in _channels(bb), "应通过视觉(多帧确认后)认出对手走子并 emit opponent 事件"


def test_anima_resigns_when_hopelessly_lost():
    # ANIMA(白) 只剩王，对方有王+皇后 → 我方视角约 -900 厘兵，且非将军/非终局
    lost = chess.Board("8/8/8/3k4/8/8/q7/7K w - - 0 1")
    assert not lost.is_game_over()
    world = FakeWorld(lost.copy())
    bb = _bb(world, lost.copy(), my_side="white")
    tree = boardgame.build_boardgame_tree(bb)

    for _ in range(config.GAME_RESIGN_CONFIRM + 1):
        tree.tick_once()

    assert bb.exit_reason == "resign", "落后约一个皇后且持续够久 → 应按引擎评分主动认输"
    assert bb.finished
    assert "end" in _channels(bb)


def test_tree_idles_when_world_phase_not_start():
    """world 还没开赛（perceive.state.phase=not_start）→ 树这拍 idle：不走子、不结束，等世界开局。"""
    world = FakeWorld()
    world.perceive = lambda: Observation(
        image_png=None, state={"controllers": {"white": "anima", "black": "bot"}, "phase": "not_start"})
    bb = _bb(world, ChessAdapter().new_state(), my_side="white")
    tree = boardgame.build_boardgame_tree(bb)
    tree.tick_once()
    assert bb.move_count == 0 and not bb.finished, "未开赛时树挂起：不驱动世界、不收尾"


def test_tree_exits_when_world_phase_game_over():
    """world 判终局（phase=game_over）→ 树收尾退出（世界是终局权威，树跟着 phase 反应）。"""
    world = FakeWorld()
    world.perceive = lambda: Observation(
        image_png=None, state={"controllers": {"white": "anima", "black": "bot"}, "phase": "game_over"})
    bb = _bb(world, ChessAdapter().new_state(), my_side="white")
    tree = boardgame.build_boardgame_tree(bb)
    tree.tick_once()
    assert bb.finished and "end" in _channels(bb), "world game_over → 树收尾"


def test_seat_lost_makes_anima_exit():
    """对局中 world 把 ANIMA 的席位换给别人（perceive 的 controllers 里 my_side != anima）→
    ANIMA 读这组角色 meta、通用地如实退出（不写棋种特判）。"""
    world = FakeWorld()
    world.perceive = lambda: Observation(   # world 说：白方现在是 human（我被换下了）
        image_png=None, state={"controllers": {"white": "human", "black": "bot"}})
    bb = _bb(world, ChessAdapter().new_state(), my_side="white")
    tree = boardgame.build_boardgame_tree(bb)

    tree.tick_once()
    assert bb.exit_reason == "seat_lost", "读 world 的 controllers 发现自己被换下 → seat_lost"
    assert bb.finished and "end" in _channels(bb)


def test_terminal_checkmate_is_detected_and_exits():
    # 傻瓜杀(Fool's mate)后的局面：白被将死，is_game_over=True
    mated = chess.Board("rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3")
    assert mated.is_checkmate()
    world = FakeWorld(mated.copy())
    bb = _bb(world, mated.copy(), my_side="white")
    tree = boardgame.build_boardgame_tree(bb)

    tree.tick_once()
    assert bb.finished, "终局应被检测到并收尾"
    assert "end" in _channels(bb), "应 emit 一条 end 事件"
    assert bb.exit_reason.startswith("terminal")
