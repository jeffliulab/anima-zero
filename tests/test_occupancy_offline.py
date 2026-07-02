"""追踪层识别器离线测试（v0.5 wave 2）：合成斜视帧 → 占用盘 → 核对真值。

合成方式：按世界侧 models.py 的材质色画一张俯视棋盘（绿板 + 白/黑圆子），再用透视变换
"斜"到一个梯形四边形里（模拟斜上方机位），灰底背景。识别器必须自己找板角、自标定、
底带采样，读回和真值一致的占用盘。真 Gazebo 斜视帧的验证在 wave 3（这里先守几何/颜色管线）。
"""
from __future__ import annotations

import chess
import cv2
import numpy as np
import pytest

from anima.tools.boardgame._occupancy_vision import OccupancyRecognizer

# 合成画面参数（画布 1280×720 模拟相机分辨率；颜色对齐世界侧 models.py 材质）
CANVAS_W, CANVAS_H = 1280, 720
BOARD_GREEN = (64, 82, 64)        # ≈ diffuse 0.25,0.32,0.25 × 255
PIECE_WHITE = (235, 230, 210)     # ≈ 0.92,0.90,0.82
PIECE_BLACK = (26, 26, 31)        # ≈ 0.10,0.10,0.12
BACKGROUND = (120, 120, 120)      # 板外灰地面
TOPDOWN_CELL = 60                 # 俯视原图每格像素
PIECE_RADIUS_FRAC = 0.32          # 圆子半径 / 格边长
# 斜视目标四边形（图中 左上/右上/右下/左下）：近大远小的梯形，模拟斜上方看盘、白方(rank1)靠相机
OBLIQUE_QUAD = [(390, 140), (890, 140), (1080, 620), (200, 620)]


def synth_oblique_frame(occ: dict[int, str]) -> bytes:
    """按占用真值 {square:'w'|'b'} 合成一张斜视帧 PNG。"""
    size = TOPDOWN_CELL * 8
    top = np.full((size, size, 3), BOARD_GREEN, np.uint8)
    for sq, color in occ.items():
        f, r = sq % 8, sq // 8
        cx = int((f + 0.5) * TOPDOWN_CELL)
        cy = int((8 - r - 0.5) * TOPDOWN_CELL)          # rank1 在图下缘（白方近相机约定）
        rgb = PIECE_WHITE if color == "w" else PIECE_BLACK
        cv2.circle(top, (cx, cy), int(TOPDOWN_CELL * PIECE_RADIUS_FRAC), rgb, -1)
    src = np.array([[0, 0], [size, 0], [size, size], [0, size]], np.float32)
    dst = np.array(OBLIQUE_QUAD, np.float32)
    m = cv2.getPerspectiveTransform(src, dst)
    canvas = cv2.warpPerspective(top, m, (CANVAS_W, CANVAS_H),
                                 borderMode=cv2.BORDER_CONSTANT, borderValue=BACKGROUND)
    ok, buf = cv2.imencode(".png", cv2.cvtColor(canvas, cv2.COLOR_RGB2BGR))
    assert ok
    return buf.tobytes()


def occ_of_board(board: chess.Board) -> dict[int, str]:
    return {sq: ("w" if p.color else "b") for sq, p in board.piece_map().items()}


@pytest.mark.parametrize("occ", [
    {},                                                   # 空盘
    {chess.E4: "w"},                                      # 单子（gazebo v0.4 形态）
    {chess.E4: "w", chess.D5: "b", chess.A1: "w", chess.H8: "b"},   # 散布四角
    occ_of_board(chess.Board()),                          # 完整开局 32 子
])
def test_occupancy_reads_synthetic_oblique_frame(occ):
    placement, uncertain = OccupancyRecognizer().read_detailed(synth_oblique_frame(occ))
    assert uncertain == set(), f"合成干净帧不该有看不清的格：{sorted(uncertain)}"
    assert placement == occ


def test_no_board_in_frame_means_everything_uncertain():
    """画面里没有板（纯灰帧）→ 整盘 64 格看不清、占用盘为空——诚实报"没看到"，绝不硬猜。"""
    canvas = np.full((CANVAS_H, CANVAS_W, 3), BACKGROUND, np.uint8)
    ok, buf = cv2.imencode(".png", canvas)
    placement, uncertain = OccupancyRecognizer().read_detailed(buf.tobytes())
    assert placement == {}
    assert len(uncertain) == 64


def test_gray_blob_on_square_is_uncertain_not_guessed():
    """格上一团中灰（机械臂/阴影，非白非黑非板绿）→ 该格"看不清"，不猜成子也不猜成空。"""
    frame = synth_oblique_frame({chess.E4: "w"})
    arr = cv2.cvtColor(cv2.imdecode(np.frombuffer(frame, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
    # 在 d5 的斜视投影位置盖一团中灰：把俯视 d5 格中心投到斜视像素
    size = TOPDOWN_CELL * 8
    src = np.array([[0, 0], [size, 0], [size, size], [0, size]], np.float32)
    m = cv2.getPerspectiveTransform(src, np.array(OBLIQUE_QUAD, np.float32))
    f, r = chess.square_file(chess.D5), chess.square_rank(chess.D5)
    pt = np.array([[[(f + 0.5) * TOPDOWN_CELL, (8 - r - 0.2) * TOPDOWN_CELL]]], np.float32)
    u, v = cv2.perspectiveTransform(pt, m)[0][0]
    cv2.circle(arr, (int(u), int(v)), 18, (128, 128, 128), -1)
    ok, buf = cv2.imencode(".png", cv2.cvtColor(arr, cv2.COLOR_RGB2BGR))

    placement, uncertain = OccupancyRecognizer().read_detailed(buf.tobytes())
    assert chess.D5 in uncertain, "中灰团块必须进 uncertain，而不是被猜成 w/b/空"
    assert placement.get(chess.E4) == "w", "别的格照常认"
