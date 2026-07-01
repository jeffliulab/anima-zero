"""对弈行为树冒烟测试：用一个内存假世界（不起 HTTP），确定性地逐拍 tick 行为树，
验证整条对弈回路——看盘(视觉)→引擎出手→发命令→认出对手走子→终局——都真的跑通。

故意【手动 tick】（不经 BehaviorRunner 的后台线程/sleep），让测试快、可复现、不依赖时间。
这是大重构"行为不变"的对照基线之一。
"""
from __future__ import annotations

import chess
from py_trees.common import Status

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


class FakePhysWorld(FakeWorld):
    """物理世界的假模型：除 move 外还支持 remove/place，并记录收到的原语序列。

    关键区别（模拟 gazebo-chess）：物理 `move` 是**裸搬子**（不判棋规——大脑才是裁判），
    所以「吃子」必须先 remove(to) 再 move；数据世界的 move 才判合法（见 FakeWorld）。
    """

    def __init__(self, board: chess.Board | None = None):
        super().__init__(board)
        self.name = "fake-phys"
        self.ops: list[tuple[str, dict]] = []

    def invoke(self, name: str, **cmd) -> ActionResult:
        self.ops.append((name, cmd))
        if name == "move":
            f, t = chess.parse_square(cmd["from"]), chess.parse_square(cmd["to"])
            p = self.board.remove_piece_at(f)
            if p is None:
                return ActionResult(ok=False, message=f"{cmd['from']} 空")
            self.board.set_piece_at(t, p)                      # 裸搬，不判棋规
            return ActionResult(ok=True, message="moved")
        if name == "remove":
            self.board.remove_piece_at(chess.parse_square(cmd["square"]))
            return ActionResult(ok=True, message="removed")
        if name == "place":
            self.board.set_piece_at(chess.parse_square(cmd["square"]),
                                    chess.Piece.from_symbol(cmd["piece"]))
            return ActionResult(ok=True, message="placed")
        return ActionResult(ok=False, message=f"未知命令 {name}")

    def capabilities(self) -> Capabilities:
        return Capabilities(name=self.name, version="test",
                            tools=[ToolSpec(n, n, {}, "tool") for n in ("move", "remove", "place")])


def _bb(world: FakeWorld, belief: chess.Board, my_side="white", prims=None) -> boardgame.BoardGameBlackboard:
    return boardgame.BoardGameBlackboard(
        world=world, adapter=ChessAdapter(), belief=belief, my_side=my_side,
        prims=set(prims) if prims else set(),
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


def test_sendmove_physical_capture_removes_then_moves():
    """新框架核心：物理世界(move+remove+place)吃子 = 先 remove(to) 再 move。
    大脑当裁判（只发合法手），世界只做裸搬——所以吃子得先把被吃子拿走，再搬子过去。"""
    # 白 d4 兵可吃黑 e5 兵
    fen = "rnbqkbnr/pppp1ppp/8/4p3/3P4/8/PPP1PPPP/RNBQKBNR w KQkq - 0 2"
    world = FakePhysWorld(chess.Board(fen))
    bb = _bb(world, chess.Board(fen), my_side="white", prims={"move", "remove", "place"})
    bb.pending_move = chess.Move.from_uci("d4e5")
    bb.pending_san = "dxe5"

    assert boardgame.SendMove(bb).update() == Status.SUCCESS
    assert [n for n, _ in world.ops] == ["remove", "move"], "吃子应拆成 remove(e5) + move(d4->e5)"
    assert world.board.piece_at(chess.E5) == chess.Piece(chess.PAWN, chess.WHITE), "白兵应到 e5"
    assert bb.move_count == 1 and bb.act_fail == 0


def test_sendmove_data_world_capture_is_single_move():
    """数据世界(只有 move)吃子 = 一条 move（世界数据层自己吞）——框架靠能力查询自动区分，无世界名特判。"""
    fen = "rnbqkbnr/pppp1ppp/8/4p3/3P4/8/PPP1PPPP/RNBQKBNR w KQkq - 0 2"
    world = FakeWorld(chess.Board(fen))            # 只有 move、且 move 判合法
    bb = _bb(world, chess.Board(fen), my_side="white", prims={"move"})
    bb.pending_move = chess.Move.from_uci("d4e5")
    bb.pending_san = "dxe5"

    assert boardgame.SendMove(bb).update() == Status.SUCCESS
    assert world.board.piece_at(chess.E5) == chess.Piece(chess.PAWN, chess.WHITE)
    assert bb.move_count == 1


def test_perceive_no_image_counts_fail_not_crash():
    """世界给不出画面（img=None）→ 计一次感知失败、这拍跳过，不崩、不静默前进（不再读 phase/controllers）。"""
    world = FakeWorld()
    world.perceive = lambda: Observation(image_png=None, state={})
    bb = _bb(world, ChessAdapter().new_state(), my_side="white")
    tree = boardgame.build_boardgame_tree(bb)
    tree.tick_once()
    assert bb.move_count == 0 and not bb.finished
    assert bb.perceive_fail == 1


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
