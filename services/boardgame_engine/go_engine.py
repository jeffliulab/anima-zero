# ⚠️ 状态：就位待接——本版无消费方，未暴露 MCP 工具（原因与接入条件见本包 README.md）。
# 源自原外部 3-anima-chess-engine/go/engine.py（v0.6 内聚搬入，算法未改）。
"""
围棋核心引擎 —— Naive 蒙特卡洛树搜索 (MCTS)，纯 CPU、无神经网络。

标准 19×19 棋盘，中国规则（区域计分），贴目 7.5。

为什么围棋不用国际象棋那套 alpha-beta？
  * 分支因子太大（19×19 开局就 361 个点），且没有“便宜又靠谱的局面评估函数”
    —— 一块棋是死是活、一片空算谁的，几乎要下完才知道。
  * MCTS 绕开这个坑：不去“评估”局面，而是从当前局面随机模拟很多盘一直下到终局
    （终局数子是明确的！），用胜率反推每一步好不好。一句话：
        “不会判断局面，那就把它下完看谁赢。”
  * 代价：19×19 的 naive 随机模拟很重，纯 Python 棋力有限——这正是历史上围棋
    必须等到 MCTS + 神经网络 (AlphaGo) 才被攻克的根本原因。

本文件分两部分：
  1. GoBoard —— 棋规（落子 / 提子 / 打劫 / 禁着点 / 数子），含为随机模拟做的加速。
  2. MCTS    —— 选择 (UCT) → 扩展 → 随机模拟 (playout) → 回传。

棋盘约定：0 = 空，1 = 黑（先手），2 = 白。PASS 用 -1 表示。
"""

import math
import random
import time

EMPTY, BLACK, WHITE = 0, 1, 2
PASS = -1


def opponent(color):
    return WHITE if color == BLACK else BLACK


# 邻居 / 对角线表按棋盘尺寸缓存（只读，可被所有 clone 共享，省内存又省时间）
_NEIGHBOR_CACHE = {}
_DIAGONAL_CACHE = {}


def _neighbor_table(n):
    if n in _NEIGHBOR_CACHE:
        return _NEIGHBOR_CACHE[n]
    res = []
    for i in range(n * n):
        r, c = divmod(i, n)
        nb = []
        # Aligned on purpose: four parallel edge cases read better as a block than as
        # eight lines. / 有意对齐：四个边界情形排成一块比拆成八行好读。
        if r > 0:     nb.append(i - n)   # noqa: E701
        if r < n - 1: nb.append(i + n)   # noqa: E701
        if c > 0:     nb.append(i - 1)   # noqa: E701
        if c < n - 1: nb.append(i + 1)   # noqa: E701
        res.append(tuple(nb))
    _NEIGHBOR_CACHE[n] = res
    return res


def _diagonal_table(n):
    if n in _DIAGONAL_CACHE:
        return _DIAGONAL_CACHE[n]
    res = []
    for i in range(n * n):
        r, c = divmod(i, n)
        dg = []
        for dr, dc in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
            rr, cc = r + dr, c + dc
            if 0 <= rr < n and 0 <= cc < n:
                dg.append(rr * n + cc)
        res.append(tuple(dg))
    _DIAGONAL_CACHE[n] = res
    return res


class GoBoard:
    """一个可快速 clone 的围棋局面（中国规则 / 区域计分）。"""

    def __init__(self, size=19, komi=7.5):
        self.size = size
        self.komi = komi
        self.board = [EMPTY] * (size * size)
        self.to_move = BLACK
        self.ko = None              # 打劫禁着点（下一手不许落的那个点）
        self.passes = 0             # 连续 pass 次数（达到 2 即终局）
        self.captured = {BLACK: 0, WHITE: 0}   # 各方“提掉对方多少子”（仅供显示）
        self._neighbors = _neighbor_table(size)
        self._diagonals = _diagonal_table(size)
        # 空点表：支持 O(1) 随机取点 / 增删（随机模拟的关键加速）
        self._empty_list = list(range(size * size))
        self._empty_pos = {i: i for i in range(size * size)}

    def clone(self):
        """快速复制（MCTS 每次模拟都要一份独立棋盘）。"""
        b = GoBoard.__new__(GoBoard)
        b.size = self.size
        b.komi = self.komi
        b.board = self.board[:]
        b.to_move = self.to_move
        b.ko = self.ko
        b.passes = self.passes
        b.captured = dict(self.captured)
        b._neighbors = self._neighbors          # 只读，共享
        b._diagonals = self._diagonals
        b._empty_list = self._empty_list[:]
        b._empty_pos = dict(self._empty_pos)
        return b

    # ---------- 空点表维护（swap-remove，O(1)） ----------
    def _remove_empty(self, idx):
        pos = self._empty_pos.pop(idx)
        last = self._empty_list[-1]
        self._empty_list[pos] = last
        self._empty_pos[last] = pos
        self._empty_list.pop()

    def _add_empty(self, idx):
        self._empty_pos[idx] = len(self._empty_list)
        self._empty_list.append(idx)

    # ---------- 棋串与气（均带提前退出，活棋一找到气就停，省去整块洪泛） ----------
    def _reaches_liberty(self, idx):
        """idx 所在棋串是否至少有一口气（找到一口立刻返回，活棋几乎瞬间命中）。"""
        board = self.board
        color = board[idx]
        stack = [idx]
        seen = {idx}
        while stack:
            s = stack.pop()
            for nb in self._neighbors[s]:
                v = board[nb]
                if v == EMPTY:
                    return True
                if v == color and nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        return False

    def _libs_at_least(self, idx, k):
        """idx 所在棋串的气是否 >= k（数到 k 就停）。"""
        board = self.board
        color = board[idx]
        stack = [idx]
        seen = {idx}
        libs = set()
        while stack:
            s = stack.pop()
            for nb in self._neighbors[s]:
                v = board[nb]
                if v == EMPTY:
                    libs.add(nb)
                    if len(libs) >= k:
                        return True
                elif v == color and nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        return len(libs) >= k

    def _group(self, idx):
        """idx 所在整块棋串的 set（仅在确实要提子时才调用）。"""
        board = self.board
        color = board[idx]
        stack = [idx]
        seen = {idx}
        while stack:
            s = stack.pop()
            for nb in self._neighbors[s]:
                if board[nb] == color and nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        return seen

    # ---------- 合法性 ----------
    def is_legal(self, idx, color):
        """idx 处对 color 是否合法落子（PASS 永远合法）。"""
        if idx == PASS:
            return True
        if self.board[idx] != EMPTY or idx == self.ko:
            return False
        opp = opponent(color)
        # 1) 有空邻居 -> 立刻有气
        for nb in self._neighbors[idx]:
            if self.board[nb] == EMPTY:
                return True
        # 走到这说明 idx 四周都是子：idx 是每个邻接棋串的一口气
        # 2) 连上自己一块、那块填掉 idx 后仍有气（>=2 口气）-> 合法
        # 3) 邻接对方一块只剩这一口气（<2）-> 能提掉 -> 合法；否则自杀
        for nb in self._neighbors[idx]:
            v = self.board[nb]
            if v == color:
                if self._libs_at_least(nb, 2):
                    return True
            elif v == opp:
                if not self._libs_at_least(nb, 2):
                    return True
        return False

    # ---------- 落子 ----------
    def play(self, idx):
        """落子（调用前应保证合法）。idx == PASS 表示虚手。"""
        color = self.to_move
        if idx == PASS:
            self.passes += 1
            self.ko = None
            self.to_move = opponent(color)
            return

        self.passes = 0
        opp = opponent(color)
        self.board[idx] = color
        self._remove_empty(idx)

        # 提掉因此没气的对方棋串（活棋一口气就停，只有真没气才整块取出）
        captured = set()
        for nb in self._neighbors[idx]:
            if self.board[nb] == opp and nb not in captured:
                if not self._reaches_liberty(nb):
                    captured |= self._group(nb)
        for c in captured:
            self.board[c] = EMPTY
            self._add_empty(c)
        if captured:
            self.captured[color] += len(captured)

        # 打劫：恰好提一子、且自己这颗是只有一口气的单子 -> 设禁着点
        new_ko = None
        if len(captured) == 1:
            if len(self._group(idx)) == 1 and not self._libs_at_least(idx, 2):
                new_ko = next(iter(captured))
        self.ko = new_ko
        self.to_move = opp

    # ---------- 真眼判断（随机模拟用，避免自己填自己的眼） ----------
    def _is_eye(self, idx, color):
        for nb in self._neighbors[idx]:
            if self.board[nb] != color:
                return False                  # 四邻必须都是自己
        diags = self._diagonals[idx]
        opp = opponent(color)
        enemy = sum(1 for d in diags if self.board[d] == opp)
        on_edge = len(diags) < 4
        return enemy == 0 if on_edge else enemy <= 1

    # ---------- 随机模拟用：快速取一个随机着法 ----------
    def random_playout_move(self, rng):
        """随机挑一个合法且非自家真眼的点；找不到就 PASS。"""
        color = self.to_move
        el = self._empty_list
        n = len(el)
        if n == 0:
            return PASS
        # 快路径：随机试几次（开局/中盘几乎一次命中）
        for _ in range(8):
            p = el[rng.randrange(n)]
            if p != self.ko and not self._is_eye(p, color) and self.is_legal(p, color):
                return p
        # 慢路径：随机顺序扫一遍，给出确定答案（避免提前 PASS 偏差）
        order = el[:]
        rng.shuffle(order)
        for p in order:
            if p != self.ko and not self._is_eye(p, color) and self.is_legal(p, color):
                return p
        return PASS

    # ---------- MCTS 扩展用：列出候选着法 ----------
    def legal_moves(self):
        """合法且非真眼的点 + PASS。"""
        color = self.to_move
        moves = [p for p in self._empty_list
                 if p != self.ko and not self._is_eye(p, color)
                 and self.is_legal(p, color)]
        moves.append(PASS)
        return moves

    def is_over(self):
        return self.passes >= 2

    # ---------- 数子（区域计分 / 中国规则） ----------
    def score(self):
        """返回 (黑域 - 白域 - 贴目)：>0 黑胜，<0 白胜。"""
        board = self.board
        black = sum(1 for v in board if v == BLACK)
        white = sum(1 for v in board if v == WHITE)
        seen = [False] * (self.size * self.size)
        for i in range(self.size * self.size):
            if board[i] != EMPTY or seen[i]:
                continue
            stack = [i]
            seen[i] = True
            region = [i]
            borders = set()
            while stack:
                s = stack.pop()
                for nb in self._neighbors[s]:
                    v = board[nb]
                    if v == EMPTY and not seen[nb]:
                        seen[nb] = True
                        stack.append(nb)
                        region.append(nb)
                    elif v != EMPTY:
                        borders.add(v)
            if borders == {BLACK}:
                black += len(region)
            elif borders == {WHITE}:
                white += len(region)
        return black - white - self.komi

    def winner(self):
        return BLACK if self.score() > 0 else WHITE


# ============================================================
#  Naive MCTS
# ============================================================
class _Node:
    __slots__ = ("move", "parent", "children", "wins", "visits",
                 "untried", "to_move")

    def __init__(self, move, parent, to_move):
        self.move = move            # 走到本结点的那一手（由 opponent(to_move) 下出）
        self.parent = parent
        self.children = []
        self.wins = 0.0             # 从“刚走完那一手的玩家”视角累计的胜数
        self.visits = 0
        self.untried = None         # 尚未展开的候选着法
        self.to_move = to_move      # 本结点轮到谁走


class MCTS:
    """Naive 蒙特卡洛树搜索：随机模拟 (light playout)，无任何启发式评估。"""

    def __init__(self, time_limit=5.0, max_iters=200000, c=1.4,
                 max_playout_len=None, rng=None):
        self.time_limit = time_limit      # 单步思考秒数上限
        self.max_iters = max_iters        # 模拟次数上限（与时间先到先停）
        self.c = c                        # UCT 探索系数
        self.max_playout_len = max_playout_len
        self.rng = rng or random.Random()
        self.last_iters = 0
        self.last_winrate = 0.0

    # ---------- UCT 选择 ----------
    def _uct_child(self, node):
        logN = math.log(node.visits)
        best, best_val = None, -1.0
        c = self.c
        for ch in node.children:
            val = ch.wins / ch.visits + c * math.sqrt(logN / ch.visits)
            if val > best_val:
                best_val, best = val, ch
        return best

    # ---------- 随机模拟到终局 ----------
    def _rollout(self, board):
        cap = self.max_playout_len or (board.size * board.size * 2)
        rng = self.rng
        steps = 0
        while not board.is_over() and steps < cap:
            board.play(board.random_playout_move(rng))
            steps += 1
        return board.winner()

    def best_move(self, root_board):
        """返回 MCTS 认为的最佳着法（点的索引或 PASS）。"""
        legal = root_board.legal_moves()
        if legal == [PASS]:
            return PASS

        root = _Node(move=None, parent=None, to_move=root_board.to_move)
        root.untried = legal[:]
        deadline = time.time() + self.time_limit

        it = 0
        while it < self.max_iters and time.time() < deadline:
            it += 1
            node = root
            board = root_board.clone()

            # 1) 选择：沿 UCT 往下，直到遇到可扩展结点或叶子
            while not node.untried and node.children:
                node = self._uct_child(node)
                board.play(node.move)

            # 2) 扩展：随机展开一个未试着法
            if node.untried:
                m = node.untried.pop(self.rng.randrange(len(node.untried)))
                board.play(m)
                child = _Node(move=m, parent=node, to_move=board.to_move)
                child.untried = board.legal_moves()
                node.children.append(child)
                node = child

            # 3) 模拟：从这里随机下到终局
            winner = self._rollout(board)

            # 4) 回传：沿途结点，赢家=走进它那一手的玩家 -> 记一胜
            while node is not None:
                node.visits += 1
                if winner == opponent(node.to_move):
                    node.wins += 1.0
                node = node.parent

        self.last_iters = it
        if not root.children:
            return PASS
        best = max(root.children, key=lambda ch: ch.visits)
        self.last_winrate = best.wins / best.visits if best.visits else 0.0
        return best.move
