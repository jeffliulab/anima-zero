"""CNN 识别器（视觉桥第二层，PIECE 空间）：斜视帧 → 每格 13 类（12 子型 + 空）+ 看不清格集合。

懂子型、但会认错（合成数据训的）——所以它**永远不单独说了算**：结论进 referee.judge 和
追踪层互检，两眼一致才采信（v1.1「不全信任何单只眼」）。与第一层**完全独立**：只共享
"板角检测+透视矫正"这一个几何步骤（单一实现防漂移），颜色/占用判定零共享。

结构（ChessCog 式）：板角→矫正→每格切一张「含子身」的高条 crop（子身向远端涂抹，crop 要
往北多包 1.2 格）→ 小 CNN 逐格 13 类 → softmax 置信度低于 VISION_CNN_CONF_MIN 的格进 uncertain。

**诚实降级（占位纪律）**：权重文件不存在 → `available() == False`，构造时不炸；launcher/裁判
据此退化成单层（占用眼 + 期望）。权重不入 git（公开仓不塞二进制），用 world/gazebo-chess/
scripts/{gen_dataset,train_cnn}.py 可复现地重训（见各自 docstring）。

推理运行时 = onnxruntime（CPU 轮子小、启动快）；训练依赖（torch）绝不进这里。
"""
from __future__ import annotations

import numpy as np

from ... import config
from . import _occupancy_vision as _ov

# ---- 与训练侧共享的契约（train_cnn.py import 这里，改了要重训！）----
CLASSES = ["", "P", "N", "B", "R", "Q", "K", "p", "n", "b", "r", "q", "k"]   # 0=空
# 每格 crop 的几何（格坐标单位；斜视下子身向远端(北)涂抹，crop 往北多包住身体）
CROP_NORTH_CELLS = 1.2    # 从格中心向北包这么多格（王的身影 ≈1.2 格）
CROP_SOUTH_CELLS = 0.35   # 从格中心向南包这么多格（底座下缘 + 一点余量）
CROP_X_MARGIN_CELLS = 0.2  # 左右各外扩
CROP_W, CROP_H = 32, 48   # 入网尺寸（宽×高）

_ALL_SQUARES = frozenset(range(64))


def crop_squares(rect: np.ndarray) -> np.ndarray:
    """矫正图 → (64, CROP_H, CROP_W, 3) float32 [0,1]，格序 = 0..63（rank*8+file）。
    训练与推理都用这一个函数切格（同一几何，训练即推理）。"""
    import cv2
    cell = config.VISION_OCC_RECT_CELL_PX
    size = rect.shape[0]
    out = np.zeros((64, CROP_H, CROP_W, 3), np.float32)
    for rank in range(8):
        cy = (8 - rank - 0.5) * cell
        y0 = int(cy - CROP_NORTH_CELLS * cell)
        y1 = int(cy + CROP_SOUTH_CELLS * cell)
        for file in range(8):
            cx = (file + 0.5) * cell
            x0 = int(cx - (0.5 + CROP_X_MARGIN_CELLS) * cell)
            x1 = int(cx + (0.5 + CROP_X_MARGIN_CELLS) * cell)
            # 越界部分用边缘复制补齐（板边格的身体可能超出矫正图）
            pad_t, pad_b = max(0, -y0), max(0, y1 - size)
            pad_l, pad_r = max(0, -x0), max(0, x1 - size)
            patch = rect[max(0, y0):min(size, y1), max(0, x0):min(size, x1)]
            if pad_t or pad_b or pad_l or pad_r:
                patch = cv2.copyMakeBorder(patch, pad_t, pad_b, pad_l, pad_r, cv2.BORDER_REPLICATE)
            out[rank * 8 + file] = cv2.resize(patch, (CROP_W, CROP_H)).astype(np.float32) / 255.0
    return out


class CnnReader:
    """PIECE 空间识别器（适配器 recognizer 协议）。权重缺失时 available()=False（诚实降级单层）。"""

    space = "piece"   # 与 base.PIECE 同串

    def __init__(self, weights_path: str | None = None) -> None:
        self._path = weights_path or config.cnn_weights_path()
        self._sess = None

    def available(self) -> bool:
        import os
        if self._sess is not None:
            return True
        if not os.path.exists(self._path):
            return False
        try:
            import onnxruntime  # noqa: F401
            return True
        except ImportError:
            return False

    def _session(self):
        if self._sess is None:
            import onnxruntime
            self._sess = onnxruntime.InferenceSession(self._path, providers=["CPUExecutionProvider"])
        return self._sess

    def read_detailed(self, image_png: bytes) -> tuple[dict, set]:
        import cv2
        frame = _ov._decode_rgb(image_png)
        if frame is None:
            return {}, set(_ALL_SQUARES)
        quad = _ov._detect_board_quad(frame)
        if quad is None:
            return {}, set(_ALL_SQUARES)     # 没找到板：整盘看不清（和追踪层同语义）
        rect = _ov._rectify(frame, quad, cv2)
        crops = crop_squares(rect)          # (64,H,W,3)
        x = crops.transpose(0, 3, 1, 2)     # NCHW
        logits = self._session().run(None, {"x": x})[0]   # (64,13)
        e = np.exp(logits - logits.max(axis=1, keepdims=True))
        probs = e / e.sum(axis=1, keepdims=True)
        placement: dict = {}
        uncertain: set = set()
        for sq in range(64):
            k = int(probs[sq].argmax())
            if float(probs[sq][k]) < config.VISION_CNN_CONF_MIN:
                uncertain.add(sq)           # 置信度不够 → 看不清，不硬猜
            elif CLASSES[k]:
                placement[sq] = CLASSES[k]
        return placement, uncertain
