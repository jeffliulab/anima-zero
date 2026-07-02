"""追踪层识别器（视觉桥第一层，OCC 空间）：斜视相机帧 → 每格「空/'w'/'b'」+ 看不清格集合。

便宜、稳、但盲——不认子型，只认占用+颜色；子型由脑内信念盘记着（belief + diff_move 同构于
Raspberry Turk 一族的「从已知局面跟踪变化」路线）。与第二层 CNN **完全独立**（不共享任何中间
结果，只在裁判 referee.judge 汇合），这是双保险成立的前提。

流水线（每拍从零重标定，抗漂移）：
  1. 找板：整帧绿色掩码 → 最大连通块 → 凸包近似出四角（找不到板 → 整盘"看不清"，绝不硬猜）。
  2. 自标定 + 矫正：四角 ↔ 棋盘格坐标做透视矫正（去斜视），方向约定按 config 四分旋转。
  3. 底带采样：每格只采**靠相机一侧、贴板面的一条带**——棋子和棋盘的接触点（底座）落在自己
     格内、受高子遮挡最小（斜视下子身会投影到后方邻格，格中心采样会误读）。
  4. 判色：带内绿占比高 → 空；非绿像素里白/黑占比够压倒 → 'w'/'b'；样本不足/灰蒙蒙（机械臂、
     阴影）→ 该格进 uncertain，交裁判"再看一眼"。

所有阈值/带宽/方向约定在 src/config.py（VISION_OCC_*，env 可覆盖）；颜色假设 = gazebo-chess 的
绿板/白黑子（世界侧 models.py 材质），真斜视帧上若光照不均需再调（诚实标注，wave 3 验证）。
格键 = 0..63 的格号（rank*8+file，与 python-chess / _vision.placement_of_board 同约定）。
"""
from __future__ import annotations

import io

import numpy as np

from ... import config

# 域常量：8×8 棋盘（定义，不是硬编码）
_FILES = 8
_RANKS = 8
_ALL_SQUARES = frozenset(range(_FILES * _RANKS))


class OccupancyRecognizer:
    """OCC 空间识别器（适配器 recognizer 协议：`space` + `read_detailed(png) -> (placement, uncertain)`）。"""

    space = "occ"   # 与 base.OCC 同串（本模块不 import base，保持零依赖纯视觉）

    def read_detailed(self, image_png: bytes) -> tuple[dict, set]:
        import cv2
        frame = _decode_rgb(image_png)
        if frame is None:
            return {}, set(_ALL_SQUARES)
        quad = _detect_board_quad(frame)
        if quad is None:
            return {}, set(_ALL_SQUARES)      # 没找到板：整盘看不清（诚实），绝不硬猜
        rect = _rectify(frame, quad, cv2)
        return _sample_bands(rect)


# ---------- 1. 解码 ----------
def _decode_rgb(image_png: bytes) -> np.ndarray | None:
    import cv2
    arr = np.frombuffer(image_png, np.uint8)
    bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if bgr is None:
        return None
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


# ---------- 2. 找板四角 ----------
def _green_mask(rgb: np.ndarray) -> np.ndarray:
    g = rgb[:, :, 1].astype(int)
    r = rgb[:, :, 0].astype(int)
    b = rgb[:, :, 2].astype(int)
    m = config.VISION_OCC_GREEN_MARGIN
    return ((g > r + m) & (g > b + m)).astype(np.uint8)


def _detect_board_quad(rgb: np.ndarray) -> np.ndarray | None:
    """整帧找绿板 → 四角像素（按图中 左上/右上/右下/左下 排序）。找不到/太小/近似不出四边形 → None。"""
    import cv2
    mask = _green_mask(rgb)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    big = max(cnts, key=cv2.contourArea)
    if cv2.contourArea(big) < config.VISION_OCC_MIN_BOARD_FRAC * rgb.shape[0] * rgb.shape[1]:
        return None
    hull = cv2.convexHull(big)
    peri = cv2.arcLength(hull, True)
    # 由松到紧试几档近似精度，取到恰好 4 个顶点为止（斜视下板是任意凸四边形，别用 minAreaRect 凑）
    for eps_frac in (0.02, 0.03, 0.05, 0.08):
        approx = cv2.approxPolyDP(hull, eps_frac * peri, True)
        if len(approx) == 4:
            return _order_corners(approx.reshape(4, 2).astype(np.float32))
    return None


def _order_corners(pts: np.ndarray) -> np.ndarray:
    """四角排成 图中[左上, 右上, 右下, 左下]（经典 和/差 排序）。"""
    s = pts.sum(axis=1)
    d = pts[:, 0] - pts[:, 1]          # u - v：右上最大、左下最小
    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmax(d)]
    bl = pts[np.argmin(d)]
    return np.array([tl, tr, br, bl], np.float32)


# ---------- 3. 透视矫正（去斜视）----------
def _rectify(rgb: np.ndarray, quad: np.ndarray, cv2) -> np.ndarray:
    """按四角把板矫正成正方形俯视图。方向约定（哪个角是 a1）由 VISION_OCC_QUARTER_TURNS 定：
    默认 0 = 相机从白方一侧看盘 → 图左下角 = a1。矫正后坐标系：x=列(a→h)、y=行(8→1)，
    即 y 越大越靠近相机（rank 越小）。"""
    q = int(config.VISION_OCC_QUARTER_TURNS) % 4
    quad = np.roll(quad, -q, axis=0)   # 旋转"哪个探测角当左上"，等价于旋转棋盘方向约定
    size = config.VISION_OCC_RECT_CELL_PX * _FILES
    dst = np.array([[0, 0], [size, 0], [size, size], [0, size]], np.float32)
    m = cv2.getPerspectiveTransform(quad, dst)
    return cv2.warpPerspective(rgb, m, (size, size))


# ---------- 4. 底带采样 + 判色 ----------
def _sample_bands(rect: np.ndarray) -> tuple[dict, set]:
    import cv2
    cell = config.VISION_OCC_RECT_CELL_PX
    band_h = max(1, int(cell * config.VISION_OCC_BAND_FRAC))
    gray = cv2.cvtColor(rect, cv2.COLOR_RGB2GRAY)
    placement: dict = {}
    uncertain: set = set()
    for rank in range(_RANKS):
        # 矫正图里 rank r 的底边 y = (8-r)*cell（y 越大越靠近相机）；带 = 底边往上 band_h 像素
        y1 = (_RANKS - rank) * cell
        y0 = y1 - band_h
        for file in range(_FILES):
            sq = rank * _FILES + file
            x0, x1 = file * cell, (file + 1) * cell
            band = rect[y0:y1, x0:x1]
            gband = gray[y0:y1, x0:x1]
            verdict = _classify_band(band, gband)
            if verdict == "?":
                uncertain.add(sq)
            elif verdict != "":
                placement[sq] = verdict
    return placement, uncertain


def _classify_band(band_rgb: np.ndarray, band_gray: np.ndarray) -> str:
    """一条底带 → ''(空) / 'w' / 'b' / '?'(看不清)。"""
    g = band_rgb[:, :, 1].astype(int)
    r = band_rgb[:, :, 0].astype(int)
    b = band_rgb[:, :, 2].astype(int)
    m = config.VISION_OCC_GREEN_MARGIN
    greenish = (g > r + m) & (g > b + m)
    non_green = band_gray[~greenish]
    non_green_frac = non_green.size / band_gray.size
    # 判空看「非绿占比」而不是「绿占比」：子底座只占底带的一部分（约 1/4），剩下全是板面绿——
    # 用"绿多=空"会把有子的格误判成空；正确语义是"非绿的东西够多=有物"。
    if non_green_frac < config.VISION_OCC_OCCUPIED_MIN_FRAC:
        return ""                                        # 板面为主 → 空格
    if non_green.size < config.VISION_OCC_MIN_BAND_PX:
        return "?"                                       # 有点东西但样本太少 → 看不清（别硬猜）
    white_frac = float((non_green > config.VISION_OCC_WHITE_THRESH).mean())
    black_frac = float((non_green < config.VISION_OCC_BLACK_THRESH).mean())
    if white_frac >= config.VISION_OCC_DOMINANCE and white_frac > black_frac:
        return "w"
    if black_frac >= config.VISION_OCC_DOMINANCE and black_frac > white_frac:
        return "b"
    return "?"                                           # 灰蒙蒙（机械臂/阴影/半遮挡）→ 看不清
