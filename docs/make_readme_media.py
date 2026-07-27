#!/usr/bin/env python3
"""出 README 的展示素材 —— 机位、动作、尺寸全写在这儿，改了场景/机器人重跑即可。

用法（要先装好 world/sim-house-nav 的依赖）：
    world/sim-house-nav/.venv/bin/python docs/make_readme_media.py go2
    world/sim-house-nav/.venv/bin/python docs/make_readme_media.py g1

⛔ 别手工截图（alice-house 那边踩过：手摆机位截的图，场景一改就全过时、还没人记得机位在哪）。

产物（写进 anima-zero/docs/images/）：
  nav-<robot>.gif    左右对照动图：左=ANIMA 唯一看得到的第一视角，右=实际发生了什么
  nav-<robot>.png    同一时刻的静帧（GIF 不能显示时的兜底，也用作社交预览）
"""
from __future__ import annotations

import io
import os
import sys
import threading
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_REPO, "world", "sim-house-nav"))
os.environ.setdefault("MUJOCO_GL", "egl")

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from sim import HouseSim  # noqa: E402

OUT = os.path.join(_HERE, "images")
# GIF 要进 README，**体积是硬约束**（GitHub 上几十 MB 的图没人等得起）。
# 三个旋钮一起拧：帧率、每一路的尺寸、调色板颜色数。
FPS = 8                    # 动图帧率（够看清步态，又不至于帧数爆炸）
TILE_W, TILE_H = 400, 300  # 每一路缩放到这么大
GIF_COLORS = 64            # 调色板颜色数：场景是低饱和的室内，64 色肉眼几乎看不出损失
GIF_STRIDE = 2             # 每隔几帧取一帧进 GIF（播放速度不变，体积减半）
GAP = 6                    # 中缝
LABEL_H = 30               # 标签条高度
FONT_DIR = "/usr/share/fonts/truetype"
TITLE_F = ImageFont.truetype(f"{FONT_DIR}/dejavu/DejaVuSans-Bold.ttf", 13)
SUB_F = ImageFont.truetype(f"{FONT_DIR}/dejavu/DejaVuSans.ttf", 11)
BG = (14, 14, 16)
# 演示路线：出生在玄关(7.3,-0.6)、朝西(180°)，客厅在东北 (x 4~9.5, y 2~10)。
# 所以先右转朝北，再直走进客厅——正对电视墙和沙发，第一视角才有内容。
# ⚠️ 第一版是"先走再转"，结果它径直撞进玄关柜，第一视角糊成一片棕色（渲出来才发现的，
#    别只看动作序列想当然）。
# 长度也是设计的一部分：README 的动图 10 秒左右最合适，太长没人看完、体积还爆。
MOVES = [("turn_right", 85), ("forward", 3.0), ("turn_left", 40), ("forward", 1.5)]


def _label(img: Image.Image, text: str, sub: str) -> Image.Image:
    """给一路画面加标题条。"""
    out = Image.new("RGB", (img.width, img.height + LABEL_H), BG)
    out.paste(img, (0, LABEL_H))
    d = ImageDraw.Draw(out)
    d.text((10, 7), text, font=TITLE_F, fill=(228, 228, 234))
    # ⚠️ 副标题的起点按**实测文字宽度**算，不是按字数乘一个猜的字宽——
    #    第一版用 7*len(text) 估，宽窄字母一混就和主标题叠在一起了。
    x = 10 + d.textlength(text, font=TITLE_F) + 14
    d.text((x, 9), sub, font=SUB_F, fill=(122, 122, 134))
    return out


def grab(sim: HouseSim) -> Image.Image | None:
    a, b = sim.frame_png(), sim.third_person_jpeg()
    if not a or not b:
        return None
    left = Image.open(io.BytesIO(a)).convert("RGB").resize((TILE_W, TILE_H))
    right = Image.open(io.BytesIO(b)).convert("RGB").resize((TILE_W, TILE_H))
    left = _label(left, "ANIMA sees this", "first-person, the only input")
    right = _label(right, "what actually happens", "for you, not for ANIMA")
    canvas = Image.new("RGB", (TILE_W * 2 + GAP, left.height), BG)
    canvas.paste(left, (0, 0))
    canvas.paste(right, (TILE_W + GAP, 0))
    return canvas


def main() -> None:
    robot = sys.argv[1] if len(sys.argv) > 1 else "go2"
    os.makedirs(OUT, exist_ok=True)
    sim = HouseSim(robot_key=robot)
    sim.start()
    time.sleep(3.0)                       # 等它站稳、两路渲染都出第一帧

    done = threading.Event()

    def drive() -> None:
        for act, arg in MOVES:
            if act == "forward":
                sim.drive_distance(arg)
            else:
                sim.drive_turn(arg, +1 if act == "turn_left" else -1)
        done.set()

    threading.Thread(target=drive, daemon=True).start()

    frames: list[Image.Image] = []
    t_end = time.time() + 60                       # 兜底：最多录 60 秒
    while not done.is_set() and time.time() < t_end:
        f = grab(sim)
        if f:
            frames.append(f)
        time.sleep(1.0 / FPS)
    for _ in range(FPS):                            # 结尾多留 1 秒静帧
        f = grab(sim)
        if f:
            frames.append(f)
        time.sleep(1.0 / FPS)
    sim.stop()

    if not frames:
        print("一帧都没抓到——渲染没起来？")
        return
    # 统一量化到一张共用调色板：逐帧各量各的会让相邻帧色彩抖动、反而更大也更花。
    picked = frames[::GIF_STRIDE]
    pal = picked[0].quantize(colors=GIF_COLORS, method=Image.MEDIANCUT)
    qs = [f.quantize(palette=pal, dither=Image.FLOYDSTEINBERG) for f in picked]
    gif = os.path.join(OUT, f"nav-{robot}.gif")
    # 抽帧后每帧多停一会儿，播放速度和实时一致（抽帧只减体积、不加速）
    qs[0].save(gif, save_all=True, append_images=qs[1:],
               duration=int(1000 / FPS * GIF_STRIDE), loop=0, optimize=True)
    still = os.path.join(OUT, f"nav-{robot}.png")
    last = frames[-FPS - 1]        # 取收尾那一帧：走到位、画面最能说明问题
    last.save(still)
    # 再单独存一份**只有第一视角**的：README 里「两副身体对照」要的是 1 对 1 的比较,
    # 直接并排两张左右分屏的合成图会变成四格、和图注对不上（2026-07-27 踩过）。
    eye = os.path.join(OUT, f"eye-{robot}.png")
    last.crop((0, LABEL_H, TILE_W, last.height)).save(eye, optimize=True)
    print(f"{gif}  {len(qs)} 帧(原 {len(frames)})  {os.path.getsize(gif) / 1e6:.1f} MB")
    print(f"{still}  {os.path.getsize(still) / 1e3:.0f} KB")


if __name__ == "__main__":
    main()
