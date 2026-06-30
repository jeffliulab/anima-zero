"""ANIMA 的眼睛（象棋）：read_board —— 对一帧棋盘画面做图像识别，认出当前棋子摆放。

吃的是**画面像素（真·视觉）**，不读世界内部数据——真机做得到的就是这个。
今天对干净合成图用**模板匹配**，可靠 100%；接口 = 「图 → 摆放」，以后接真实摄像头
只把这个识别器换成更强的视觉模型即可，上层（行为树/工具/skill）一行不改。

【外观约定】下面常量/画法必须与 world/sim-chess/render.py 的"棋盘物理外观"一致——
这相当于"知道棋子长什么样"（real vision 也得知道），不是读内部状态。两边一致性由
round-trip 测试（render→read 100% 一致，见 tests/test_vision_roundtrip.py）守住。
"""
from __future__ import annotations

import io

import chess
from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat

from ... import config

# ---- "棋盘物理外观"共享规格：必须与 sim-chess/render.py 完全一致（命名常量，非可调；两侧逐像素对齐，
#      由 round-trip 测试守一致）。字体路径走发现式（config.discover_board_font），不写死绝对路径。----
CELL = 64
N = 8
SIZE = CELL * N
LIGHT_SQ = (240, 217, 181)
DARK_SQ = (181, 136, 99)
WHITE_DISK = (248, 248, 248)
BLACK_DISK = (38, 38, 38)
WHITE_TEXT = (20, 20, 20)
BLACK_TEXT = (235, 235, 235)
DISK_R = 26
FONT_SIZE = 40
# 协议用的"子型字母"(P/N/B/R/Q/K)——move 命令的 piece 标识(域常量,见 chess.py to_command);不是画法。
LETTER = {chess.PAWN: "P", chess.KNIGHT: "N", chess.BISHOP: "B",
          chess.ROOK: "R", chess.QUEEN: "Q", chess.KING: "K"}
# 棋子【字形】(画法,与协议字母分开):白方空心子 ♔♕♖♗♘♙、黑方实心子 ♚♛♜♝♞♟。**必须与 render.py 的 GLYPH 完全一致**。
GLYPH = {
    chess.WHITE: {chess.KING: "♔", chess.QUEEN: "♕", chess.ROOK: "♖",
                  chess.BISHOP: "♗", chess.KNIGHT: "♘", chess.PAWN: "♙"},
    chess.BLACK: {chess.KING: "♚", chess.QUEEN: "♛", chess.ROOK: "♜",
                  chess.BISHOP: "♝", chess.KNIGHT: "♞", chess.PAWN: "♟"},
}
PIECE_TYPES = (chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KING)

_font = None


def _get_font():
    global _font
    if _font is None:
        path = config.discover_board_font()
        try:
            _font = ImageFont.truetype(path, FONT_SIZE) if path else ImageFont.load_default(size=FONT_SIZE)
        except Exception:
            _font = ImageFont.load_default(size=FONT_SIZE)
    return _font


def _cell_light(file: int, row: int) -> bool:
    return (file + row) % 2 == 0


def _render_cell(light: bool, piece) -> Image.Image:
    """画一个单元格(背景=格色; piece=(ptype,color) 或 None)。与 render.py 的每格画法一致。"""
    img = Image.new("RGB", (CELL, CELL), LIGHT_SQ if light else DARK_SQ)
    if piece is not None:
        ptype, color = piece
        d = ImageDraw.Draw(img)
        cx = cy = CELL // 2
        disk = WHITE_DISK if color == chess.WHITE else BLACK_DISK
        txt = WHITE_TEXT if color == chess.WHITE else BLACK_TEXT
        d.ellipse([cx - DISK_R, cy - DISK_R, cx + DISK_R, cy + DISK_R],
                  fill=disk, outline=(0, 0, 0), width=2)
        ch = GLYPH[color][ptype]
        f = _get_font()
        bb = d.textbbox((0, 0), ch, font=f)
        w, h = bb[2] - bb[0], bb[3] - bb[1]
        d.text((cx - w / 2 - bb[0], cy - h / 2 - bb[1]), ch, fill=txt, font=f)
    return img


_TEMPLATES = None


def _templates():
    """每种格色一套模板：空 + 12 子；键=子符号('P'/'n'/...) 或 None(空)。"""
    global _TEMPLATES
    if _TEMPLATES is None:
        t = {True: {}, False: {}}
        for light in (True, False):
            t[light][None] = _render_cell(light, None)
            for color in (chess.WHITE, chess.BLACK):
                for ptype in PIECE_TYPES:
                    sym = chess.Piece(ptype, color).symbol()
                    t[light][sym] = _render_cell(light, (ptype, color))
        _TEMPLATES = t
    return _TEMPLATES


def _sad(a: Image.Image, b: Image.Image) -> float:
    return float(sum(ImageStat.Stat(ImageChops.difference(a, b)).sum))


def read_board_detailed(image_png: bytes) -> tuple[dict, set]:
    """画面 → (摆放 {square: 子符号}, 看不清的格子集合 uncertain)。

    每格用 **Lowe 比值检验**判置信度：算这格与所有模板的 SAD，取最像(best)与次像(second)，
    `best/second > VISION_AMBIGUITY_RATIO` 说明"最像的"和"第二像的"差不多像 = 分不清 → 标该格"看不清"。
    干净合成图上 best≈0、二者差距极大、比值≈0，永不误触发（由 round-trip 测试守住）；真机噪声下才会触发。
    阈值进 config（具名 + env 可覆盖），不是拍脑袋的魔法数。
    """
    img = Image.open(io.BytesIO(image_png)).convert("RGB")
    if img.size != (SIZE, SIZE):
        img = img.resize((SIZE, SIZE))
    T = _templates()
    placement: dict[int, str] = {}
    uncertain: set[int] = set()
    for sq in chess.SQUARES:
        file = chess.square_file(sq)
        row = 7 - chess.square_rank(sq)          # 白方在下
        light = _cell_light(file, row)
        cell = img.crop((file * CELL, row * CELL, file * CELL + CELL, row * CELL + CELL))
        best, best_sad, second_sad = None, float("inf"), float("inf")
        for sym, tpl in T[light].items():
            s = _sad(cell, tpl)
            if s < best_sad:
                best_sad, second_sad, best = s, best_sad, sym
            elif s < second_sad:
                second_sad = s
        ratio = (best_sad / second_sad) if second_sad > 0 else 0.0
        if ratio > config.VISION_AMBIGUITY_RATIO:
            uncertain.add(sq)
        if best is not None:
            placement[sq] = best                 # 仍给出最佳猜测（uncertain 标记由上层决定要不要采信）
    return placement, uncertain


def read_board(image_png: bytes) -> dict:
    """画面 → {square(0..63): 子符号 'P'/'n'/...}。**只认棋子摆放**（不含轮次/易位权——画面里没有）。

    只要摆放（最佳猜测），不含置信度；需要"看不清"信息时用 read_board_detailed。
    """
    return read_board_detailed(image_png)[0]


def placement_of_board(board: chess.Board) -> dict:
    """一个 python-chess Board 的摆放 → {square: 符号}（用来和 read_board 的结果比对）。"""
    return {sq: p.symbol() for sq, p in board.piece_map().items()}
