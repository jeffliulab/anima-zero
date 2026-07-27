"""把虚拟桌面、画布和笔渲染成一张 PNG —— sim-desk 这个世界自己的「画面」。"""
from __future__ import annotations

import io

from PIL import Image, ImageDraw

GW, GH = 32, 24  # 画布网格:32 列 × 24 行(每格 20px,正好铺满 640×480);world.py 也用这套


def render_desk(pen: list[float], canvas: set | None = None, w: int = 640, h: int = 480, fmt: str = "PNG") -> bytes:
    img = Image.new("RGB", (w, h), (222, 205, 170))  # 木色桌面
    d = ImageDraw.Draw(img)
    d.rectangle([10, 10, w - 10, h - 10], outline=(120, 90, 60), width=4)
    # 画布:已涂黑的格子(铺在桌面上,笔画在它上面)
    if canvas:
        cw, ch = w / GW, h / GH
        for (r, c) in canvas:
            d.rectangle([c * cw, r * ch, (c + 1) * cw, (r + 1) * ch], fill=(30, 30, 30))
    px, py = int(pen[0] * w), int(pen[1] * h)
    d.line([px - 28, py + 28, px + 28, py - 28], fill=(40, 40, 40), width=8)  # 笔杆
    d.polygon(
        [(px + 28, py - 28), (px + 18, py - 16), (px + 16, py - 18)],
        fill=(210, 170, 70),  # 笔尖
    )
    buf = io.BytesIO()
    img.save(buf, format=fmt)  # PNG 给 /perceive(大脑用);JPEG 给 /stream(实时视频)
    return buf.getvalue()
