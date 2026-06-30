"""sim-chess 渲染：把棋盘画成干净的俯视图。

这张图既是 `perceive` 给大脑当"摄像头画面"的东西，也是 `/stream` 的帧。

【棋盘外观约定 —— 重要】
下面这套常量+画法 = "这盘棋在物理上长什么样"。大脑侧的视觉识别器
(anima/skills/chess_vision.py 的 read_board) 必须按同一套约定才能可靠读回。
所以这里是"共享的物理外观规格"，两边的常量/字形要一致（real life 里这就是物理）。
白方在下（rank1 在底部），标准俯视。
"""
from __future__ import annotations

import io
import os

import chess
from PIL import Image, ImageDraw, ImageFont

# ---- 共享外观规格（命名常量，两边逐像素一致；非可调）----
CELL = 64
N = 8
SIZE = CELL * N                       # 512
LIGHT_SQ = (240, 217, 181)            # 浅格
DARK_SQ = (181, 136, 99)              # 深格
WHITE_DISK = (248, 248, 248)          # 白子的圆盘
BLACK_DISK = (38, 38, 38)             # 黑子的圆盘
WHITE_TEXT = (20, 20, 20)             # 白子上的字（深色）
BLACK_TEXT = (235, 235, 235)          # 黑子上的字（浅色）
DISK_R = 26
FONT_SIZE = 40
# 人类选子高亮圈（只在有人正选着子时画；默认不画→渲染↔视觉一致不受影响）。
# 画在格子边沿、圈住棋子，醒目但尽量不糊住中心棋子；world 模拟真实世界，这圈也进给大脑的画面（有意）。
SEL_R = 30
SEL_W = 4
SEL_COLOR = (250, 204, 21)            # 金黄高亮
# 协议用的"子型字母"(P/N/B/R/Q/K,大写、与颜色无关)——是 move(from,to,piece) 命令里的 piece 标识,
# 世界拿它核对大脑的识别(见 world.py _anima_move)。是域常量(像 FEN 符号),不是画法。
LETTER = {chess.PAWN: "P", chess.KNIGHT: "N", chess.BISHOP: "B",
          chess.ROOK: "R", chess.QUEEN: "Q", chess.KING: "K"}
# 棋子【字形】(画法,与协议字母分开):白方空心子 ♔♕♖♗♘♙、黑方实心子 ♚♛♜♝♞♟(U+2654..265F)。
# 形状即棋种,一眼能认出王后车象马兵;圆盘底色+字色再区分黑白。两侧(render/vision)必须逐像素一致。
GLYPH = {
    chess.WHITE: {chess.KING: "♔", chess.QUEEN: "♕", chess.ROOK: "♖",
                  chess.BISHOP: "♗", chess.KNIGHT: "♘", chess.PAWN: "♙"},
    chess.BLACK: {chess.KING: "♚", chess.QUEEN: "♛", chess.ROOK: "♜",
                  chess.BISHOP: "♝", chess.KNIGHT: "♞", chess.PAWN: "♟"},
}

# 字体走发现式（跨发行版/系统），可用 env ANIMA_BOARD_FONT 覆盖；不写死绝对路径。
_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:\\Windows\\Fonts\\arialbd.ttf",
    os.path.expanduser("~/.fonts/DejaVuSans-Bold.ttf"),
]


def _discover_font() -> str | None:
    env = os.getenv("ANIMA_BOARD_FONT")
    if env and os.path.exists(env):
        return env
    for p in _FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


_font = None


def get_font():
    global _font
    if _font is None:
        path = _discover_font()
        try:
            _font = ImageFont.truetype(path, FONT_SIZE) if path else ImageFont.load_default(size=FONT_SIZE)
        except Exception:
            _font = ImageFont.load_default(size=FONT_SIZE)
    return _font


def cell_is_light(file: int, row: int) -> bool:
    """屏幕坐标(file 0..7 左→右, row 0..7 上→下)的格子是不是浅格。a1(左下)=深格。"""
    return (file + row) % 2 == 0


def draw_piece(draw: ImageDraw.ImageDraw, cx: int, cy: int, piece) -> None:
    """在格中心 (cx,cy) 画一个棋子(piece=chess.Piece 或 None=空)。"""
    if piece is None:
        return
    disk = WHITE_DISK if piece.color == chess.WHITE else BLACK_DISK
    txt = WHITE_TEXT if piece.color == chess.WHITE else BLACK_TEXT
    draw.ellipse([cx - DISK_R, cy - DISK_R, cx + DISK_R, cy + DISK_R],
                 fill=disk, outline=(0, 0, 0), width=2)
    ch = GLYPH[piece.color][piece.piece_type]
    f = get_font()
    bbox = draw.textbbox((0, 0), ch, font=f)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((cx - w / 2 - bbox[0], cy - h / 2 - bbox[1]), ch, fill=txt, font=f)


def square_to_screen(sq: int) -> tuple[int, int]:
    """棋盘格 square → 屏幕 (file, row)。白方在下：rank1 在底部 row=7。"""
    file = chess.square_file(sq)
    rank = chess.square_rank(sq)
    return file, 7 - rank


def render_board(board: chess.Board, selected_sq: str | None = None) -> Image.Image:
    """把一个 python-chess Board 画成 512x512 俯视图。

    selected_sq：人类当前选中的格（如 "e2"），给它画个高亮圈；None=没人选子→不画
    （默认 None 保证渲染↔视觉 round-trip 一致，不影响视觉识别）。这张图同时喂 /stream 和 perceive，
    所以圈也会进给大脑的画面——这是有意的（真实世界里"人拿起了哪个子"本就看得见）。"""
    img = Image.new("RGB", (SIZE, SIZE), LIGHT_SQ)
    d = ImageDraw.Draw(img)
    # 棋盘格底色
    for row in range(N):
        for file in range(N):
            x0, y0 = file * CELL, row * CELL
            color = LIGHT_SQ if cell_is_light(file, row) else DARK_SQ
            d.rectangle([x0, y0, x0 + CELL - 1, y0 + CELL - 1], fill=color)
    # 棋子
    for sq in chess.SQUARES:
        file, row = square_to_screen(sq)
        cx, cy = file * CELL + CELL // 2, row * CELL + CELL // 2
        draw_piece(d, cx, cy, board.piece_at(sq))
    # 人类选中的子：画高亮圈（仅当 selected_sq 有效时）
    if selected_sq:
        try:
            s = chess.parse_square(selected_sq.strip().lower())
        except Exception:
            s = None
        if s is not None:
            file, row = square_to_screen(s)
            cx, cy = file * CELL + CELL // 2, row * CELL + CELL // 2
            d.ellipse([cx - SEL_R, cy - SEL_R, cx + SEL_R, cy + SEL_R], outline=SEL_COLOR, width=SEL_W)
    return img


def to_png(img: Image.Image) -> bytes:
    b = io.BytesIO()
    img.save(b, "PNG")
    return b.getvalue()


def to_jpeg(img: Image.Image, quality: int = 80) -> bytes:
    b = io.BytesIO()
    img.save(b, "JPEG", quality=quality)
    return b.getvalue()
