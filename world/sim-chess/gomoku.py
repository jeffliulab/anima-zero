"""五子棋：sim-chess 世界进程里【可切换的第二种棋】的真值棋盘 + 渲染 + 内置 bot。

为什么放在 sim-chess 里：world = 模拟真实世界，这个进程模拟的"现实"可以是象棋桌、也可以是五子棋桌。
人在世界网页上点"切五子棋"，传输的画面瞬间变五子棋——用来测 ANIMA（还拿着象棋视觉/适配器）对
"世界突然换了棋盘"的反应。**ANIMA 侧不为此加任何东西**：它只能从画面察觉异常、靠现成的通用容错处理。

这套五子棋是【真的】（真落子、真判五连、真有个会挑威胁点的 bot），不是摆样子；可调数字 env 可覆盖，无写死。
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw

SIZE = int(os.getenv("SIMGOMOKU_SIZE", "15"))     # 15×15 标准盘
WIN = 5                                           # 五连胜（域常量）
_DIRS = ((0, 1), (1, 0), (1, 1), (1, -1))         # 横/竖/两斜

# ---- 渲染外观（命名常量；五子棋没有大脑侧视觉对手，纯给人看 + 给 ANIMA 当"陌生画面"）----
CELL_G = int(os.getenv("SIMGOMOKU_CELL", "34"))   # 每格像素
BOARD_BG = (222, 184, 135)                        # 木色棋盘
LINE_COLOR = (90, 60, 30)
STONE_R = CELL_G // 2 - 3
BLACK_STONE = (24, 24, 24)
WHITE_STONE = (245, 245, 245)
SEL_COLOR = (220, 40, 40)


def _opp(color: str) -> str:
    return "white" if color == "black" else "black"


class GomokuBoard:
    """五子棋真值盘：黑先；place 落子、winner 判五连、bot_move 内置棋手走一步。"""

    def __init__(self) -> None:
        self.grid: list[list[str | None]] = [[None] * SIZE for _ in range(SIZE)]
        self.turn = "black"                       # 黑先（域规则）
        self.moves: list[tuple[int, int, str]] = []

    def copy(self) -> "GomokuBoard":
        g = GomokuBoard.__new__(GomokuBoard)
        g.grid = [row[:] for row in self.grid]
        g.turn = self.turn
        g.moves = list(self.moves)
        return g

    def in_bounds(self, r: int, c: int) -> bool:
        return 0 <= r < SIZE and 0 <= c < SIZE

    def place(self, r: int, c: int, color: str | None = None) -> tuple[bool, str]:
        """落子（color 省略=当前轮到的一方）。非法（越界/有子/没轮到/已终局）则返回 (False, 原因)。"""
        color = color or self.turn
        if self.winner() is not None:
            return False, "棋局已结束"
        if not self.in_bounds(r, c):
            return False, f"越界 ({r},{c})"
        if self.grid[r][c] is not None:
            return False, f"({r},{c}) 已有子"
        if color != self.turn:
            return False, f"还没轮到{color}"
        self.grid[r][c] = color
        self.moves.append((r, c, color))
        self.turn = _opp(color)
        return True, f"落子 {color} ({r},{c})"

    def _line_len(self, r: int, c: int, color: str, dr: int, dc: int) -> int:
        """从 (r,c) 沿 (dr,dc) 单向数同色连子（含起点假定为 color）。"""
        n = 1
        rr, cc = r + dr, c + dc
        while self.in_bounds(rr, cc) and self.grid[rr][cc] == color:
            n += 1
            rr += dr
            cc += dc
        return n

    def winner(self) -> str | None:
        for r in range(SIZE):
            for c in range(SIZE):
                col = self.grid[r][c]
                if col is None:
                    continue
                for dr, dc in _DIRS:
                    # 只从一段的起点数，避免重复：前一格不是同色才算起点
                    pr, pc = r - dr, c - dc
                    if self.in_bounds(pr, pc) and self.grid[pr][pc] == col:
                        continue
                    if self._line_len(r, c, col, dr, dc) >= WIN:
                        return col
        return None

    def is_over(self) -> bool:
        return self.winner() is not None or len(self.moves) >= SIZE * SIZE

    def result(self) -> str:
        w = self.winner()
        if w == "black":
            return "black_win"
        if w == "white":
            return "white_win"
        return "draw" if self.is_over() else ""

    def side_to_move(self) -> str:
        return self.turn

    def move_count(self) -> int:
        return len(self.moves)

    # ---- 内置 bot：真的挑威胁点（进攻自己最长线 + 防住对手最长线），不是乱下 ----
    def _potential(self, r: int, c: int, color: str) -> int:
        """假设 color 落在 (r,c)，四个方向里能形成的最长连子长度（粗略威胁度）。"""
        best = 0
        for dr, dc in _DIRS:
            length = self._line_len(r, c, color, dr, dc) + self._line_len(r, c, color, -dr, -dc) - 1
            best = max(best, length)
        return best

    def _near_stone(self, r: int, c: int, radius: int = 2) -> bool:
        for dr in range(-radius, radius + 1):
            for dc in range(-radius, radius + 1):
                rr, cc = r + dr, c + dc
                if self.in_bounds(rr, cc) and self.grid[rr][cc] is not None:
                    return True
        return False

    def bot_move(self) -> tuple[bool, str]:
        """内置棋手走一步：空盘走天元；否则在已有子附近挑进攻+防守综合最优的点。"""
        if self.winner() is not None:
            return False, "棋局已结束"
        if not self.moves:
            return self.place(SIZE // 2, SIZE // 2)
        me, opp = self.turn, _opp(self.turn)
        best, best_score, fallback = None, -1.0, None
        for r in range(SIZE):
            for c in range(SIZE):
                if self.grid[r][c] is not None:
                    continue
                fallback = fallback or (r, c)
                if not self._near_stone(r, c):
                    continue
                # 进攻权重略高于防守；自己能成 5 直接最高分
                score = self._potential(r, c, me) * 1.05 + self._potential(r, c, opp)
                if score > best_score:
                    best_score, best = score, (r, c)
        target = best or fallback
        return self.place(*target) if target else (False, "无处可走")


# ---------------- 渲染 ----------------
def render_gomoku(board: GomokuBoard, selected=None) -> Image.Image:
    """把五子棋盘画成俯视图（格内落子）。selected=(r,c) 时画个红框提示（人类页用；五子棋单击即落，一般不用）。"""
    px = SIZE * CELL_G
    img = Image.new("RGB", (px, px), BOARD_BG)
    d = ImageDraw.Draw(img)
    # 网格线（画在格中心连成的线，棋子落在格中心）
    for i in range(SIZE):
        x = i * CELL_G + CELL_G // 2
        d.line([(x, CELL_G // 2), (x, px - CELL_G // 2)], fill=LINE_COLOR, width=1)
        d.line([(CELL_G // 2, x), (px - CELL_G // 2, x)], fill=LINE_COLOR, width=1)
    # 棋子
    for r in range(SIZE):
        for c in range(SIZE):
            col = board.grid[r][c]
            if col is None:
                continue
            cx, cy = c * CELL_G + CELL_G // 2, r * CELL_G + CELL_G // 2
            fill = BLACK_STONE if col == "black" else WHITE_STONE
            d.ellipse([cx - STONE_R, cy - STONE_R, cx + STONE_R, cy + STONE_R],
                      fill=fill, outline=(0, 0, 0), width=1)
    if selected is not None:
        r, c = selected
        x0, y0 = c * CELL_G, r * CELL_G
        d.rectangle([x0, y0, x0 + CELL_G - 1, y0 + CELL_G - 1], outline=SEL_COLOR, width=3)
    return img


def cell_from_xy(x: int, y: int, board_px: int) -> tuple[int, int]:
    """网页点击的像素坐标 → (row, col)。board_px=渲染图边长（前端按它归一化）。"""
    cell = board_px / SIZE
    c = max(0, min(SIZE - 1, int(x // cell)))
    r = max(0, min(SIZE - 1, int(y // cell)))
    return r, c


def board_px() -> int:
    return SIZE * CELL_G
