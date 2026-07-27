#!/usr/bin/env python3
"""Build the web app and place it where the Python package will carry it.

    python scripts/build_ui.py

`pip install anima` has to give someone a usable interface on a machine with no node, so
the wheel carries a pre-built copy of the web app. Building it is therefore part of making
a release, not part of making the frontend.

⚠️ This couples two build systems, and the failure mode is quiet: a wheel built without
running this first ships whatever copy happens to be sitting in `src/presentation/web/` —
possibly one from weeks ago — and a stale interface looks exactly like a working one.
Nothing errors. That is why the backend prints the UI's build time on startup, and why this
step belongs in CI rather than in anyone's memory.

构建网页，并把它放到 Python 包会带上的位置。

    python scripts/build_ui.py

`pip install anima` 必须让一台没有 node 的机器也有可用界面，所以 wheel 里带一份预先构建好的网页。
因此**构建它是发版的一部分**，不是做前端的一部分。

⚠️ 这把两套构建系统耦合在了一起，而且失败方式是**安静的**：没先跑这一步就打的 wheel，会把
`src/presentation/web/` 里碰巧留着的那份发出去——可能是几周前的——而一个过时的界面看起来和正常的
一模一样。**什么都不会报错。** 这就是后端启动时要打印网页构建时间的原因，也是这一步该写进 CI、
而不是指望谁记得的原因。
"""
from __future__ import annotations

import datetime
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
OUT = FRONTEND / "out"
DEST = ROOT / "src" / "presentation" / "web"
# 构建时间戳的文件名。server.py 用同一个名字读它——两边必须一致。
BUILD_STAMP = ".build-time"


def main() -> int:
    if not (FRONTEND / "node_modules").is_dir():
        print("先装前端依赖：cd frontend && npm ci", file=sys.stderr)
        return 1

    print("构建网页（静态导出）…")
    r = subprocess.run(["npm", "run", "build:static"], cwd=FRONTEND)
    if r.returncode != 0:
        return r.returncode
    if not (OUT / "index.html").exists():
        print(f"构建跑完了，但 {OUT}/index.html 不在——产物路径变了？", file=sys.stderr)
        return 1

    # Replaced wholesale rather than merged: a leftover file from an older build would be
    # served alongside the new ones and nobody would know which was which.
    # 整个替换而不是合并：旧构建残留的文件会和新文件一起被端出去，而没人分得清哪个是哪个。
    if DEST.exists():
        shutil.rmtree(DEST)
    shutil.copytree(OUT, DEST)

    # ⛔ Stamp the build time into a file rather than leaving it to be read off the file's
    # mtime. `pip install` rewrites mtimes to the moment of installation, so an installed
    # copy always looked freshly built — the staleness check failed in exactly the case it
    # was written for, and only worked in a development checkout where it was least needed.
    # Caught by installing 1.1.0 from PyPI and finding it claim a build time six hours after
    # the actual build.
    # ⛔ 把构建时间**写进文件**，而不是留给别人去读文件的 mtime。`pip install` 会把 mtime 重写成
    #    安装那一刻，于是**任何装出来的副本都显示"刚刚构建"**——这道防线在它唯一要防的场景里失效，
    #    只在最不需要它的开发目录里有效。是从 PyPI 装了 1.1.0、发现它报出的构建时间比真实构建
    #    晚了六个小时，才抓到的。
    (DEST / BUILD_STAMP).write_text(
        datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), encoding="utf-8")

    n = sum(1 for _ in DEST.rglob("*") if _.is_file())
    print(f"✓ 网页已放到 {DEST.relative_to(ROOT)}（{n} 个文件）")
    print("  现在 `anima serve` 会自己把它端出来，不需要 node。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
