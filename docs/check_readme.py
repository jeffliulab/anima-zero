#!/usr/bin/env python3
"""检查两份 README 的图片与链接 —— ⛔ 按**已入库的内容**查，不是按本地文件系统。

为什么强调这一点（2026-07-27 真踩过）：
我写了个检查脚本用 `os.path.exists()` 验图片，全绿；但那四张界面截图**从来没 git add 过**。
本地看得见、GitHub 上是裂图。**别人看到的是仓库里的内容，不是我硬盘上的内容。**

用法：
    python docs/check_readme.py            # 查工作区已暂存/已提交的状态（HEAD + index）
    python docs/check_readme.py --ref main # 查某个 ref 上的状态（推送前拿它验默认分支）
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

READMES = ("README.md", "README_zh.md")


def in_tree(path: str, ref: str | None) -> bool:
    """这个路径在 git 里吗？ref 为空 = 查 index（含刚 git add 的），否则查那个 ref。

    ⚠️ 用 ls-tree / ls-files，别用 `cat-file -e`：**目录和子模块不是 blob**，
    cat-file 一律查不到，会把 `src/clients`、`world/sim-desk` 这类正常引用报成失效
    （第一版就是这么误报了 14 条）。
    """
    path = path.rstrip("/")
    if ref:
        r = subprocess.run(["git", "ls-tree", ref, "--", path], capture_output=True, text=True)
    else:
        r = subprocess.run(["git", "ls-files", "--cached", "--", path], capture_output=True, text=True)
    return bool(r.stdout.strip())


def read(path: str, ref: str | None) -> str | None:
    target = f"{ref}:{path}" if ref else f":{path}"
    r = subprocess.run(["git", "show", target], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def anchor(heading: str) -> str:
    """GitHub 的锚点规则（够用即可）：小写、去标点、空格换连字符。"""
    h = heading.lower().replace("⭐", "").strip()
    h = re.sub(r"[^\w\s一-鿿-]", "", h).strip()
    return h.replace(" ", "-")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default=None, help="查哪个 ref（默认查 index，即已暂存的状态）")
    args = ap.parse_args()

    bad = 0
    for md in READMES:
        s = read(md, args.ref)
        if s is None:
            print(f"❌ {md} 不在 {'index' if not args.ref else args.ref} 里")
            bad += 1
            continue

        # 图片与本地链接
        targets = (re.findall(r'<img src="([^"]+)"', s)
                   + re.findall(r"!\[[^\]]*\]\(([^)]+)\)", s)
                   + re.findall(r"\]\((?!http|#)([^)]+)\)", s)
                   + re.findall(r"`((?:src|world|frontend|docs|eval|services|tests)/[A-Za-z0-9_./-]+)`", s))
        for t in sorted(set(targets)):
            if t.startswith("http"):
                continue
            p = t.split("#")[0]
            if not in_tree(p, args.ref):
                extra = "（本地有，但没入库！）" if os.path.exists(p) else ""
                print(f"❌ {md}: {p} 不在库里{extra}")
                bad += 1

        # 目录锚点
        anchors = {anchor(h) for h in re.findall(r"^#{1,3} (.+)$", s, re.M)}
        for a in re.findall(r"\]\(#([^)]+)\)", s):
            if a not in anchors:
                print(f"❌ {md}: 目录锚点 #{a} 跳不到任何标题")
                bad += 1

    # 文体门槛：上一版写成了规格表（541 行 / 58 行表格 / 140 处加粗），这几条是防复发的护栏。
    # 标杆是本机上的 Isaac Lab（141 行 / 7 / 5）与 Unitree RL Lab（150 行 / 3 / 3）。
    LIMITS = {"行": 200, "表格行": 16, "加粗": 20, "符号": 0}
    for md in READMES:
        s = read(md, args.ref) or ""
        got = {
            "行": len(s.splitlines()),
            "表格行": len(re.findall(r"^\|", s, re.M)),
            "加粗": len(re.findall(r"\*\*", s)) // 2,
            "符号": len(re.findall(r"⛔|⚠️|⭐", s)),
        }
        for k, cap in LIMITS.items():
            if got[k] > cap:
                print(f"❌ {md}: {k} {got[k]}，超过上限 {cap}")
                bad += 1
        # ⚠️ 只看**开头**那道反引号：闭合行天生不带语言标记，把它也算进来会误报。
        fences = re.findall(r"^```.*$", s, re.M)
        bare_open = [f for i, f in enumerate(fences) if i % 2 == 0 and f.strip() == "```"]
        # 目录树这类纯文本块本来就不该有语言标记，允许一个
        if len(bare_open) > 1:
            print(f"❌ {md}: 有 {len(bare_open)} 个无语言标记的代码块（ASCII 框图？）")
            bad += 1

    # 两份结构对齐
    counts = [len(re.findall(r"^## ", read(md, args.ref) or "", re.M)) for md in READMES]
    if len(set(counts)) > 1:
        print(f"❌ 两份 README 结构不对齐：二级标题 {dict(zip(READMES, counts))}")
        bad += 1

    print("✅ 全部通过" if not bad else f"\n共 {bad} 处问题")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
