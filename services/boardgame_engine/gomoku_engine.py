# ⚠️ 状态：就位待接——本版无消费方，未暴露 MCP 工具（原因与接入条件见本包 README.md）。
# 源自原外部 3-anima-chess-engine/gomoku/engine.py（v0.6 内聚搬入，算法未改）。
"""
五子棋核心引擎 —— 纯搜索算法（无神经网络）。

算法概要：
  * 棋型评估 (pattern evaluation)：把每条线映射成字符串，用模式表打分。
  * Alpha-Beta 负极大搜索 (negamax + alpha-beta pruning)。
  * 迭代加深 + 移动排序 + 邻域候选裁剪 (iterative deepening, move ordering)。
  * 一步杀 / 一步防 的战术捷径，保证不漏明显的胜负手。

棋盘约定：0 = 空，1 = 黑（先手），2 = 白。
"""

import time

N = 15                      # 棋盘边长
EMPTY, BLACK, WHITE = 0, 1, 2

WIN_SCORE = 10_000_000      # 连成五子

# 棋型模式表（站在“己方=X，空=_，对方或墙=O”的视角）
# 数值差距拉大，使得即使有少量重复计数也不影响搜索决策。
PATTERNS = [
    ("XXXXX",   WIN_SCORE),   # 五连
    ("_XXXX_",  500_000),     # 活四（必胜）
    ("XXXX_",   50_000),      # 冲四
    ("_XXXX",   50_000),
    ("XXX_X",   50_000),      # 跳冲四
    ("X_XXX",   50_000),
    ("XX_XX",   50_000),
    ("_XXX_",   5_000),       # 活三
    ("_XX_X_",  5_000),       # 跳活三
    ("_X_XX_",  5_000),
    ("XXX__",   500),         # 眠三
    ("__XXX",   500),
    ("_XX_",    200),         # 活二
    ("__XX__",  200),
    ("_X_X_",   200),
]

OPP_WEIGHT = 1.1            # 防守略重于进攻


def _count_overlap(s, sub):
    """统计 sub 在 s 中出现的次数（允许重叠）。"""
    c = start = 0
    while True:
        i = s.find(sub, start)
        if i == -1:
            break
        c += 1
        start = i + 1
    return c


def _score_line(line):
    """对单条字符串线打分。"""
    score = 0
    for pat, val in PATTERNS:
        if pat in line:                       # 先快速判断，绝大多数命中失败
            score += val * _count_overlap(line, pat)
    return score


class Gomoku:
    def __init__(self):
        self.board = [[EMPTY] * N for _ in range(N)]
        self.history = []          # [(r, c, player), ...]

    # ---------- 基础操作 ----------
    def reset(self):
        self.board = [[EMPTY] * N for _ in range(N)]
        self.history = []

    def in_bounds(self, r, c):
        return 0 <= r < N and 0 <= c < N

    def place(self, r, c, player):
        self.board[r][c] = player
        self.history.append((r, c, player))

    def undo(self):
        if not self.history:
            return None
        r, c, _ = self.history.pop()
        self.board[r][c] = EMPTY
        return r, c

    def is_empty(self):
        return not self.history

    # ---------- 胜负判断 ----------
    def check_win(self, r, c):
        """判断最后落在 (r,c) 的子是否连成五。"""
        player = self.board[r][c]
        if player == EMPTY:
            return False
        for dr, dc in ((1, 0), (0, 1), (1, 1), (1, -1)):
            cnt = 1
            for sign in (1, -1):
                rr, cc = r + dr * sign, c + dc * sign
                while self.in_bounds(rr, cc) and self.board[rr][cc] == player:
                    cnt += 1
                    rr += dr * sign
                    cc += dc * sign
            if cnt >= 5:
                return True
        return False

    # ---------- 评估 ----------
    def _player_score(self, player):
        """对整盘扫描，返回 player 的棋型总分。"""
        b = self.board
        total = 0

        def to_str(cells):
            # 两端补 'O'（墙），让边界等同被对方封堵
            chars = ['O']
            for v in cells:
                chars.append('X' if v == player else ('_' if v == EMPTY else 'O'))
            chars.append('O')
            return ''.join(chars)

        # 行
        for r in range(N):
            total += _score_line(to_str(b[r]))
        # 列
        for c in range(N):
            total += _score_line(to_str([b[r][c] for r in range(N)]))
        # 主对角线（左上->右下）
        for s in range(-(N - 1), N):
            cells = [b[r][r - s] for r in range(N) if 0 <= r - s < N]
            if len(cells) >= 5:
                total += _score_line(to_str(cells))
        # 副对角线（右上->左下）
        for s in range(2 * N - 1):
            cells = [b[r][s - r] for r in range(N) if 0 <= s - r < N]
            if len(cells) >= 5:
                total += _score_line(to_str(cells))
        return total

    def evaluate(self, player):
        """以 player 视角的整盘静态评估。"""
        opp = WHITE if player == BLACK else BLACK
        return self._player_score(player) - int(self._player_score(opp) * OPP_WEIGHT)

    # ---------- 局部评估（用于排序 / 战术捷径） ----------
    def _point_lines(self, r, c, player):
        """假设在 (r,c) 落 player 子，返回 4 个方向的窗口字符串（中心=X）。"""
        b = self.board
        out = []
        for dr, dc in ((1, 0), (0, 1), (1, 1), (1, -1)):
            chars = []
            for k in range(-4, 5):
                if k == 0:
                    chars.append('X')
                    continue
                rr, cc = r + dr * k, c + dc * k
                if self.in_bounds(rr, cc):
                    v = b[rr][cc]
                    chars.append('X' if v == player else ('_' if v == EMPTY else 'O'))
                else:
                    chars.append('O')
            out.append(''.join(chars))
        return out

    def point_score(self, r, c, player):
        """在 (r,c) 落 player 子的局部得分（含成五）。"""
        return sum(_score_line(s) for s in self._point_lines(r, c, player))

    def makes_five(self, r, c, player):
        for s in self._point_lines(r, c, player):
            if "XXXXX" in s:
                return True
        return False

    # ---------- 候选着法 ----------
    def candidates(self, radius=2):
        """返回所有“距已有棋子 radius 之内”的空点。"""
        b = self.board
        if self.is_empty():
            return [(N // 2, N // 2)]
        cand = set()
        for (r, c, _) in self.history:
            for dr in range(-radius, radius + 1):
                for dc in range(-radius, radius + 1):
                    rr, cc = r + dr, c + dc
                    if self.in_bounds(rr, cc) and b[rr][cc] == EMPTY:
                        cand.add((rr, cc))
        return list(cand)


class AI:
    def __init__(self, player=WHITE, max_depth=4, branch=10, time_limit=4.0):
        self.player = player
        self.opp = BLACK if player == WHITE else WHITE
        self.max_depth = max_depth
        self.branch = branch
        self.time_limit = time_limit
        self._deadline = 0.0

    def _ordered_moves(self, game, player, branch):
        """按局部攻防价值排序，截取前 branch 个候选。"""
        opp = BLACK if player == WHITE else WHITE
        scored = []
        for (r, c) in game.candidates():
            atk = game.point_score(r, c, player)      # 我落子的进攻价值
            dfn = game.point_score(r, c, opp)          # 对方若落此点的威胁
            scored.append((atk + dfn, r, c))
        scored.sort(reverse=True)
        return [(r, c) for _, r, c in scored[:branch]]

    def _negamax(self, game, depth, alpha, beta, player):
        if time.time() > self._deadline:
            raise TimeoutError

        if depth == 0:
            return game.evaluate(player)

        moves = self._ordered_moves(game, player, self.branch)
        if not moves:
            return game.evaluate(player)

        opp = BLACK if player == WHITE else WHITE
        best = -float("inf")
        for (r, c) in moves:
            if game.makes_five(r, c, player):
                # 立即获胜：越快越好（depth 越大代表越早）
                return WIN_SCORE + depth
            game.place(r, c, player)
            try:
                val = -self._negamax(game, depth - 1, -beta, -alpha, opp)
            finally:
                game.undo()
            if val > best:
                best = val
            if val > alpha:
                alpha = val
            if alpha >= beta:
                break
        return best

    def best_move(self, game):
        """返回 AI 的最佳落点 (r, c)。"""
        if game.is_empty():
            return (N // 2, N // 2)

        # 战术捷径 1：自己一步杀
        for (r, c) in game.candidates():
            if game.makes_five(r, c, self.player):
                return (r, c)
        # 战术捷径 2：对方一步杀 -> 封堵
        threats = [(r, c) for (r, c) in game.candidates()
                   if game.makes_five(r, c, self.opp)]
        if len(threats) == 1:
            return threats[0]

        # 迭代加深搜索
        self._deadline = time.time() + self.time_limit
        best_move = None
        moves = self._ordered_moves(game, self.player, self.branch)
        if not moves:
            return game.candidates()[0]
        best_move = moves[0]

        for depth in range(2, self.max_depth + 1):
            alpha, beta = -float("inf"), float("inf")
            current_best = None
            best_val = -float("inf")
            try:
                for (r, c) in moves:
                    if game.makes_five(r, c, self.player):
                        return (r, c)
                    game.place(r, c, self.player)
                    try:
                        val = -self._negamax(game, depth - 1, -beta, -alpha, self.opp)
                    finally:
                        game.undo()
                    if val > best_val:
                        best_val = val
                        current_best = (r, c)
                    if val > alpha:
                        alpha = val
            except TimeoutError:
                break
            if current_best is not None:
                best_move = current_best
                # 把当前最优排到最前，提升下一轮剪枝效率
                moves.remove(best_move)
                moves.insert(0, best_move)
                if best_val >= WIN_SCORE:
                    break
        return best_move
