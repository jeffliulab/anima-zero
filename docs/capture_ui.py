#!/usr/bin/env python3
"""出 README 的**界面**截图 —— 机位(URL、窗口尺寸、语言)全写在这儿,改了界面重跑即可。

⛔ 别手工截图。手截的图,界面一改就过时,而且没人记得当初截的是哪个状态。

⚠️ 最关键的一张是「思考过程展开」:历史回合的思考区默认是折叠的,而 headless Chrome
   **只能截页面初始渲染、点不了鼠标**。解法不是去改产品默认值,而是——
   **趁一轮正在跑的时候截**:实时回合的思考区本来就是自动展开的。
   本脚本用 `--live` 做这件事:后台起一轮真实对话,等它跑起来再截。

用法(要先起好 世界:8112 / 后端:8000 / 网页:3000):
    python docs/capture_ui.py                 # 全出(中英各一套)
    python docs/capture_ui.py chat --live     # 只出"对话中"那张,且跑一轮真对话
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
OUT = os.path.join(HERE, "images")

CHROME = "google-chrome"
WEB = os.getenv("ANIMA_WEB", "http://localhost:3000")
WORLD = os.getenv("HOUSENAV_WEB", "http://localhost:8112")

# 每张图:名字 → (URL, 窗口宽, 窗口高, 说明)
SHOTS = {
    # ?expand=all:把思考区摊开。headless 截图点不了鼠标,而这一轮由后台 CLI 跑、
    # 浏览器只是旁观者(对它来说是历史回合、默认折叠),所以靠地址栏参数指定。
    "chat": (f"{WEB}/?expand=all", 1680, 1150, "ANIMA 交互前端:传感区两块 + 思考过程 + 笔记本"),
    # ?live=0：不开实时流量那条 SSE。⛔ 不加的话根本截不出图——headless 浏览器只要页面上
    # 还挂着一条不结束的连接,就永远等不到"加载完成"(实测挂满 240 秒、零输出)。
    "awi": (f"{WEB}/awi?live=0", 1680, 2400, "AWI 仪表盘:协议四区(Tools/Resources/Prompts/Status)"),
    # ⚠️ 世界自己的人类页**没进 README**:它是各世界自带的独立 HTML、不属于 ANIMA 前端,
    #    也没接 i18n(英文 README 里配一张纯中文的页面很违和)。留着这条机位是给排障用的。
    "world": (WORLD, 1400, 900, "sim-house 世界自己的人类页（排障用，不进 README）"),
}

# 语言 → (Chrome 的 --lang, 文件名后缀)。界面首次访问跟随浏览器语言,所以用它就能切。
#
# ⛔ **只出英文和中文两套,别给新语言加一行**(2026-07-29 Jeff 定)。截图是**展示界面长什么样**,
# 不是展示界面说什么话——英文那张对任何语言的读者都够用。中文这套留着是因为它本来就在;
# 日文及以后的任何语言,README 里一律引用 `ui-chat-en.png`。
# 理由:每加一门语言就多一套要重截的图,而界面一改,忘了重截的那几套会**悄悄过时**
# ——静默过时正是这个仓一再踩的坑(见 ROADMAP R7)。少一套图 = 少一处会骗人的地方。
LANGS = {"en": ("en-US", "-en"), "zh": ("zh-CN", "-zh")}

LIVE_SAY = "去客厅"          # 跑一轮真对话用的指令(短、稳定、画面有内容)
LIVE_BRAIN = "gpt-5.5"
# 等这一轮跑到"有思考内容、但还没收尾"的那个窗口再截。
# ⚠️ 截晚了这一轮就跑完了——收尾后前端会用会话记录重绘,变成**历史回合、思考区折叠**,
#    白截。2026-07-27 用 25 秒就晚了(「去客厅」实测 29 秒跑完)。env 可调。
LIVE_WAIT_S = int(os.getenv("CAPTURE_LIVE_WAIT_S", "14"))
# 页面加载多久后强制出图。⚠️ 给短了会拍到"数据还没到"的空壳——
# AWI 仪表盘要先 fetch /api/awi 再渲世界卡片,12 秒拍出来是一片空白(实测踩过)。
SHOT_TIMEOUT_MS = int(os.getenv("CAPTURE_SHOT_TIMEOUT_MS", "25000"))


def shoot(url: str, w: int, h: int, lang_flag: str, path: str) -> None:
    subprocess.run(
        [CHROME, "--headless", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
         f"--lang={lang_flag}", f"--window-size={w},{h}",
         # ⛔ 必须用 --timeout(到点强制出图),不能只靠 --virtual-time-budget。
         #    AWI 仪表盘开着一条 SSE 长连接(实时流量),Chrome 永远等不到"网络空闲",
         #    只给 virtual-time-budget 的话进程会一直挂着、一张图都不写(实测挂满 240 秒)。
         f"--timeout={SHOT_TIMEOUT_MS}", "--virtual-time-budget=12000",
         f"--screenshot={path}", url],
        capture_output=True, timeout=SHOT_TIMEOUT_MS / 1000 + 60, check=False)
    # 以文件写没写出来为准,不看返回码。
    size = os.path.getsize(path) / 1e3 if os.path.exists(path) else 0
    print(f"  {os.path.basename(path):22s} {size:6.0f} KB" + ("" if size else "   ❌ 没出图"))


def start_live_turn() -> threading.Thread:
    """后台跑一轮真实对话,好让截图里的思考区是展开的、有内容的。"""
    def run() -> None:
        subprocess.run(
            [os.path.join(REPO, ".venv/bin/python"), "-m", "anima.dev_turn",
             "--world", "sim-house-nav", "--say", LIVE_SAY, "--brain", LIVE_BRAIN],
            cwd=REPO, capture_output=True, timeout=600)
    th = threading.Thread(target=run, daemon=True)
    th.start()
    return th


def main() -> None:
    which = [a for a in sys.argv[1:] if not a.startswith("--")] or list(SHOTS)
    live = "--live" in sys.argv
    os.makedirs(OUT, exist_ok=True)

    if live:
        print(f"后台起一轮真实对话（说「{LIVE_SAY}」），等 {LIVE_WAIT_S} 秒…")
        start_live_turn()
        time.sleep(LIVE_WAIT_S)

    for name in which:
        url, w, h, desc = SHOTS[name]
        print(f"{name} — {desc}")
        for lang, (flag, suffix) in LANGS.items():
            shoot(url, w, h, flag, os.path.join(OUT, f"ui-{name}{suffix}.png"))
    print("\n⛔ 截完必须打开看一眼:该出现的内容真的在画面里吗？"
          "（2026-07-26 就交过一张空会话的图）")


if __name__ == "__main__":
    main()
