"""围棋(go)——本轮**只展示板子**的占位实现（你定的）。

可落子（黑白交替）、能渲染一张标准 19×19 棋盘，用来做「切棋盘」时让画面瞬间变、测 ANIMA 反应。
**没有胜负规则**（不提子、不打劫、不数目）——`is_over()` 恒 False、`result()` 恒空。完整围棋以后再补。
界面会标注「未完整实现」。可调数字 env 可覆盖，无写死。
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw

SIZE = int(os.getenv("SIMGO_SIZE", "19"))          # 19×19 标准盘
CELL_G = int(os.getenv("SIMGO_CELL", "26"))
BOARD_BG = (219, 179, 122)                          # 木色
LINE_COLOR = (70, 45, 20)
STONE_R = CELL_G // 2 - 2
BLACK_STONE = (20, 20, 20)
WHITE_STONE = (245, 245, 245)
STAR_R = 3                                          # 星位点


def _opp(color: str) -> str:
    return "white" if color == "black" else "black"


class GoBoard:
    """占位围棋盘：只管落子 + 轮换（黑先）。无任何胜负/提子规则。"""

    def __init__(self) -> None:
        self.grid: list[list[str | None]] = [[None] * SIZE for _ in range(SIZE)]
        self.turn = "black"
        self.moves: list[tuple[int, int, str]] = []

    def copy(self) -> "GoBoard":
        g = GoBoard.__new__(GoBoard)
        g.grid = [row[:] for row in self.grid]
        g.turn = self.turn
        g.moves = list(self.moves)
        return g

    def in_bounds(self, r: int, c: int) -> bool:
        return 0 <= r < SIZE and 0 <= c < SIZE

    def place(self, r: int, c: int, color: str | None = None) -> tuple[bool, str]:
        color = color or self.turn
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

    def side_to_move(self) -> str:
        return self.turn

    def move_count(self) -> int:
        return len(self.moves)

    # 占位：围棋胜负本轮不做
    def winner(self) -> str | None:
        return None

    def is_over(self) -> bool:
        return False

    def result(self) -> str:
        return ""


def render_go(board: GoBoard, selected=None) -> Image.Image:
    """画一张 19×19 围棋盘（棋子落在交叉点）。右上角标注「未完整实现」。"""
    px = SIZE * CELL_G
    img = Image.new("RGB", (px, px), BOARD_BG)
    d = ImageDraw.Draw(img)
    for i in range(SIZE):
        x = i * CELL_G + CELL_G // 2
        d.line([(x, CELL_G // 2), (x, px - CELL_G // 2)], fill=LINE_COLOR, width=1)
        d.line([(CELL_G // 2, x), (px - CELL_G // 2, x)], fill=LINE_COLOR, width=1)
    for sr in (3, 9, 15):                            # 星位（标准 19 路）
        for sc in (3, 9, 15):
            cx, cy = sc * CELL_G + CELL_G // 2, sr * CELL_G + CELL_G // 2
            d.ellipse([cx - STAR_R, cy - STAR_R, cx + STAR_R, cy + STAR_R], fill=LINE_COLOR)
    for r in range(SIZE):
        for c in range(SIZE):
            col = board.grid[r][c]
            if col is None:
                continue
            cx, cy = c * CELL_G + CELL_G // 2, r * CELL_G + CELL_G // 2
            fill = BLACK_STONE if col == "black" else WHITE_STONE
            d.ellipse([cx - STONE_R, cy - STONE_R, cx + STONE_R, cy + STONE_R],
                      fill=fill, outline=(0, 0, 0), width=1)
    d.text((6, 4), "go (placeholder · 未完整实现)", fill=(120, 80, 40))
    return img


def cell_from_xy(x: int, y: int, board_px: int) -> tuple[int, int]:
    cell = board_px / SIZE
    c = max(0, min(SIZE - 1, int(x // cell)))
    r = max(0, min(SIZE - 1, int(y // cell)))
    return r, c


def board_px() -> int:
    return SIZE * CELL_G
