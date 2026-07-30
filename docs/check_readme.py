#!/usr/bin/env python3
"""检查各语言版文档的图片与链接 —— ⛔ 按**已入库的内容**查，不是按本地文件系统。

为什么强调这一点（2026-07-27 真踩过）：
我写了个检查脚本用 `os.path.exists()` 验图片，全绿；但那四张界面截图**从来没 git add 过**。
本地看得见、GitHub 上是裂图。**别人看到的是仓库里的内容，不是我硬盘上的内容。**

第二条教训（2026-07-29，翻译件搬进 docs/i18n/ 那次）：
链接是**相对写它的那个文件**的，不是相对仓根。翻译件搬进子目录后，里面写的是
`../../images/nav-g1.gif`；第一版脚本把这串原样丢给 git 去查，等于去仓外面找，
一查一个失效。所以 `](...)` 与 `<img src>` 一律先按**文件所在目录**换算成仓根路径再查；
而反引号里那种 `` `src/config.py` `` 是行文里提到的路径、天然从仓根说起，保持原样。

用法：
    python docs/check_readme.py            # 查工作区已暂存/已提交的状态（HEAD + index）
    python docs/check_readme.py --ref main # 查某个 ref 上的状态（推送前拿它验默认分支）
"""
from __future__ import annotations

import argparse
import os
import posixpath
import re
import subprocess
import sys

# 一份文档有几个语言版本，各自住在哪。⛔ 这是一个「全集」：加语言只能**追加**，
# 加完记得三处一起动 —— 这里、`scripts/selfcheck.py` 的 CHANGELOGS、各文档顶部的语言徽章。
LANG_DIRS = {
    "en": "",  # 英文版留在仓根：GitHub 靠根目录的 CODE_OF_CONDUCT / CONTRIBUTING / SECURITY 点亮「社区标准」
    "zh": "docs/i18n/zh",
    "ja": "docs/i18n/ja",
    "fr": "docs/i18n/fr",
    "es": "docs/i18n/es",
}

# 每种语言都该有的六份根文档
DOC_NAMES = (
    "README.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "SECURITY.md",
    "ROADMAP.md",
)

ALL_DOCS = tuple(posixpath.join(d, n) for d in LANG_DIRS.values() for n in DOC_NAMES)
READMES = tuple(posixpath.join(d, "README.md") for d in LANG_DIRS.values())


def in_tree(path: str, ref: str | None) -> bool:
    """这个路径在 git 里吗？ref 为空 = 查 index（含刚 git add 的），否则查那个 ref。

    ⚠️ 用 ls-tree / ls-files，别用 `cat-file -e`：**目录和子模块不是 blob**，
    cat-file 一律查不到，会把 `src/clients` 这类正常引用报成失效
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


def is_external(target: str) -> bool:
    """http(s):// 、mailto: 这类外链不归本脚本管。"""
    return "://" in target or target.startswith("mailto:")


def from_repo_root(md: str, target: str) -> str | None:
    """把某份文档里写的相对链接，换算成从仓根出发的路径；指到仓外面就返回 None。"""
    p = posixpath.normpath(posixpath.join(posixpath.dirname(md), target))
    return None if p == ".." or p.startswith("../") else p


def check_links(md: str, s: str, ref: str | None) -> int:
    """图片、本地链接、行文里提到的路径，逐个确认在库里。返回问题数。"""
    bad = 0

    # 这三类是**相对写它的那个文件**的
    relative = (re.findall(r'<img src="([^"]+)"', s)
                + re.findall(r"!\[[^\]]*\]\(([^)]+)\)", s)
                + re.findall(r"\]\((?!http|#)([^)]+)\)", s))
    for t in sorted(set(relative)):
        if is_external(t):
            continue
        raw = t.split("#")[0]
        if not raw:  # 纯锚点链接，交给锚点检查
            continue
        p = from_repo_root(md, raw)
        if p is None:
            print(f"❌ {md}: {raw} 指到了仓库外面")
            bad += 1
            continue
        if not in_tree(p, ref):
            extra = "（本地有，但没入库！）" if os.path.exists(p) else ""
            print(f"❌ {md}: {raw} → {p} 不在库里{extra}")
            bad += 1

    # 反引号里提到的源码路径，从仓根说起
    for p in sorted(set(re.findall(
            r"`((?:src|world|frontend|docs|eval|services|tests)/[A-Za-z0-9_./-]+)`", s))):
        if not in_tree(p, ref):
            extra = "（本地有，但没入库！）" if os.path.exists(p) else ""
            print(f"❌ {md}: {p} 不在库里{extra}")
            bad += 1

    # 目录锚点
    anchors = {anchor(h) for h in re.findall(r"^#{1,3} (.+)$", s, re.M)}
    for a in re.findall(r"\]\(#([^)]+)\)", s):
        if a not in anchors:
            print(f"❌ {md}: 目录锚点 #{a} 跳不到任何标题")
            bad += 1

    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default=None, help="查哪个 ref（默认查 index，即已暂存的状态）")
    args = ap.parse_args()

    bad = 0
    text: dict[str, str] = {}
    for md in ALL_DOCS:
        s = read(md, args.ref)
        if s is None:
            print(f"❌ {md} 不在 {'index' if not args.ref else args.ref} 里")
            bad += 1
            continue
        text[md] = s
        bad += check_links(md, s, args.ref)

    # 文体门槛（只管 README）：上一版写成了规格表（541 行 / 58 行表格 / 140 处加粗），
    # 这几条是防复发的护栏。标杆是本机上的 Isaac Lab（141 行 / 7 / 5）与 Unitree RL Lab（150 行 / 3 / 3）。
    #
    # ⛔ 2026-07-29 起**不再限制总行数**（原来是 200 行）。原因：那次事故要命的是**密度不是长度**——
    # 一篇又长又是人话的 README 没问题，一篇短但全是表格和加粗的 README 才是规格表。
    # 长度限制还会实打实挡路（当时两份 README 正好卡在 200 行，加一张动图都加不进去）。
    # 取消长度上限之后，下面三条反而变成更硬的约束：可以变长，但不许靠堆表格和加粗变长。
    LIMITS = {"表格行": 16, "加粗": 20, "符号": 0}
    for md in READMES:
        s = text.get(md)
        if s is None:
            continue
        got = {
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

    # 各语言版之间对齐。这两条是**相对比较**，不含任何绝对行数，所以内容长大它们跟着长大。
    present = [md for md in READMES if md in text]
    if len(present) > 1:
        counts = {md: len(re.findall(r"^## ", text[md], re.M)) for md in present}
        if len(set(counts.values())) > 1:
            print(f"❌ 各语言版 README 结构不对齐：二级标题 {counts}")
            bad += 1

        # 某个语言版单独发胖、或悄悄少翻了一大段，行数会先露馅。
        LENGTH_PARITY = 0.25  # 允许的行数偏差：中日英表达密度本来就不同，四分之一是留给语言差异的余量
        lines = {md: len(text[md].splitlines()) for md in present}
        lo, hi = min(lines.values()), max(lines.values())
        if lo and (hi - lo) / lo > LENGTH_PARITY:
            print(f"❌ 各语言版 README 长度差得太多（超过 {LENGTH_PARITY:.0%}）：{lines}")
            bad += 1

    print("✅ 全部通过" if not bad else f"\n共 {bad} 处问题")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
