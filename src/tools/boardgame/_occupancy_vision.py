"""追踪层识别器（视觉桥第一层，OCC 空间）：斜视相机帧 → 每格「空/'w'/'b'」+ 看不清格集合。

便宜、稳、但盲——不认子型，只认占用+颜色；子型由脑内信念盘记着（belief + diff_move 同构于
Raspberry Turk 一族的「从已知局面跟踪变化」路线）。与第二层 CNN **完全独立**（不共享任何中间
结果，只在裁判 referee.judge 汇合），这是双保险成立的前提。

流水线（每拍从零重标定，抗漂移）：
  1. 找板：整帧绿色掩码 → 最大连通块 → 凸包近似出四角（找不到板 → 整盘"看不清"，绝不硬猜）。
  2. 自标定 + 矫正：四角 ↔ 棋盘格坐标做透视矫正（去斜视），方向约定按 config 四分旋转。
  3. 底带采样：每格只采**从格中心向相机一侧延伸的一条窄带**。账（真斜视帧上校准）：子底座
     在格中心、子身向远端涂抹 ≈ 子高/tan(俯角)（50° 下兵≈0.76 格、王≈1.13 格）——带放在中心
     偏近端，本格底座的下半部在带里，而近邻子身最多够到中心以南 ~0.37 格、够不着 0.22 的带。
     （格远端/格南缘都会被别的子身染色，不能采。）
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
    """板面绿判定：绝对差（亮处）或相对比（阴影里的暗绿也算绿——否则棋子阴影会被当成'有东西'）。"""
    g = rgb[:, :, 1].astype(int)
    r = rgb[:, :, 0].astype(int)
    b = rgb[:, :, 2].astype(int)
    m = config.VISION_OCC_GREEN_MARGIN
    rel = config.VISION_OCC_GREEN_REL
    return (((g > r + m) & (g > b + m)) | ((g > r * rel) & (g > b * rel))).astype(np.uint8)


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


# ---------- 4. 底带采样 + 判色（两遍：先原始判定，再做南邻子身的遮挡剔除）----------
def _sample_bands(rect: np.ndarray) -> tuple[dict, set]:
    """斜视的固有遮挡（真帧上校准的账）：南邻格的子**身体**必然涂抹进本格采样带
    （子身在板面上的投影长 ≈ 子高/tan(俯角)，50° 下王 ≈1.2 格 + 子半径）。
    对策=南→北扫掠：一旦判定 (f,r) 有子，处理 (f,r+1) 时先把该子身所在的**像素列**从带里
    剔掉、只用剩余列的证据判——子身是窄柱（≤半格宽），剩下的半格带足够看清是板面绿（空）
    还是另一枚子的宽底座（占用）。剔完没剩多少证据 → 诚实"看不清"。"""
    import cv2
    cell = config.VISION_OCC_RECT_CELL_PX
    band_h = max(1, int(cell * config.VISION_OCC_BAND_FRAC))
    gray = cv2.cvtColor(rect, cv2.COLOR_RGB2GRAY)
    placement: dict = {}
    uncertain: set = set()
    for rank in range(_RANKS):                            # 南(rank 0)→北：南格结论先定，才能剔它的身
        # 矫正图里 rank r 的格中心 y = (8-r-0.5)*cell（y 越大越靠近相机）；带 = 中心向近端 band_h 像素
        y0 = int((_RANKS - rank - 0.5) * cell)
        y1 = y0 + band_h
        for file in range(_FILES):
            sq = rank * _FILES + file
            x0, x1 = file * cell, (file + 1) * cell
            band = rect[y0:y1, x0:x1]
            gband = gray[y0:y1, x0:x1]
            south_sq = sq - _FILES
            occluded = rank > 0 and south_sq in placement
            verdict = _classify_band(band, gband, exclude_invader=occluded)
            if verdict == "?":
                uncertain.add(sq)
            elif verdict != "":
                placement[sq] = verdict
    return placement, uncertain


def _band_green(band_rgb: np.ndarray) -> np.ndarray:
    g = band_rgb[:, :, 1].astype(int)
    r = band_rgb[:, :, 0].astype(int)
    b = band_rgb[:, :, 2].astype(int)
    m = config.VISION_OCC_GREEN_MARGIN
    rel = config.VISION_OCC_GREEN_REL
    return ((g > r + m) & (g > b + m)) | ((g > r * rel) & (g > b * rel))


def _classify_band(band_rgb: np.ndarray, band_gray: np.ndarray, exclude_invader: bool = False) -> str:
    """一条底带 → ''(空) / 'w' / 'b' / '?'(看不清)。

    exclude_invader=True（南邻有子）：先把带里**最宽的一段连续非绿列**（= 南邻子身的柱子）
    剔掉，只用剩余列判——否则南邻的身体会被误读成本格有子。
    """
    greenish = _band_green(band_rgb)
    if exclude_invader:
        col_nong = (~greenish).mean(axis=0)               # 每列非绿占比
        run = _widest_run(col_nong > 0.5)
        # 只剔【窄】段（南邻子身的头/上身柱 ≤半格宽）；宽段（≥0.55 格）是本格底座的证据，保留。
        if run is not None and (run[1] - run[0]) <= band_gray.shape[1] * config.VISION_OCC_INVADER_MAX_RUN_FRAC:
            keep = np.ones(band_gray.shape[1], bool)
            keep[run[0]:run[1]] = False
            band_gray = band_gray[:, keep]
            greenish = greenish[:, keep]
    non_green = band_gray[~greenish]
    non_green_frac = non_green.size / max(1, band_gray.size)
    # 判空看「非绿占比」而不是「绿占比」：子底座只占底带的一部分（约 1/4），剩下全是板面绿——
    # 用"绿多=空"会把有子的格误判成空；正确语义是"非绿的东西够多=有物"。
    if non_green_frac < config.VISION_OCC_OCCUPIED_MIN_FRAC:
        return ""                                        # 板面为主 → 空格
    if non_green.size < config.VISION_OCC_MIN_BAND_PX:
        return "?"                                       # 有点东西但样本太少 → 看不清（别硬猜）
    med = float(np.median(non_green))
    if med >= config.VISION_OCC_WHITE_THRESH:
        return "w"
    if med <= config.VISION_OCC_BLACK_THRESH:
        return "b"
    return "?"                                           # 中位数落在空档带（机械臂/半遮挡）→ 看不清


def _widest_run(mask: np.ndarray) -> tuple[int, int] | None:
    """一维布尔数组里最宽的一段连续 True，返回 (起, 止)；没有 True → None。"""
    best, cur_start, cur_len, best_len = None, None, 0, 0
    for i, v in enumerate(mask):
        if v:
            if cur_start is None:
                cur_start = i
            cur_len += 1
            if cur_len > best_len:
                best, best_len = (cur_start, i + 1), cur_len
        else:
            cur_start, cur_len = None, 0
    return best
