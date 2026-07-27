#!/usr/bin/env python3
"""Project self-checks — the house rules, enforced by machine instead of by memory.

These four checks used to live in a maintainer's private notes, which means a contributor
had no way of knowing they existed. They are the rules most likely to quietly break once
more than one person touches the code, so they run in CI on every push.

    python scripts/selfcheck.py             # all checks
    python scripts/selfcheck.py --tag v1.1  # also assert the tag matches the version

Exit code is non-zero if any check fails.

项目自检 —— 把「靠记性守的规矩」变成「靠机器守的规矩」。

这四条检查原先只写在维护者的私人笔记里，外部贡献者根本无从知道它们存在；而它们恰恰是
一旦多人协作就最先悄悄崩掉的规矩。所以让它们在 CI 里每次推送都跑。

任一检查不过则退出码非零。
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# --- check 1: the orchestrator must stay task-agnostic --------------------------------
# The generic ReAct loop must not know what game/task it is driving. Anything
# task-specific belongs in the world (a separate process), never up here.
# 通用 ReAct 主循环不许认识它在驱动什么任务。任务专属的东西属于「世界」(独立进程)，绝不上浮。
ORCHESTRATOR = Path("src/core/orchestrator.py")
TASK_SPECIFIC_WORDS = [
    # English identifiers / vocabulary that only make sense for a board game
    "my_side", "move_count", "game_name", "chess", "gomoku", "checkmate", "resign",
    # 中文：一旦出现这些词，说明棋类逻辑又爬回主循环了
    "执方", "手数", "对局", "对弈", "悔棋", "认输", "下棋", "棋",
]

# --- check 2: no dead config -----------------------------------------------------------
# Every constant re-exported from config.py must actually be consumed somewhere.
# config.py 里 re-export 的每个常量都必须真有人用，否则就是没人认领的雷。
CONFIG_FILE = Path("src/config.py")
CONFIG_CONSUMERS = ["src", "services", "world", "tests", "scripts"]

# --- check 3: no unregistered placeholders ---------------------------------------------
# A placeholder is allowed, but only if it was declared to the user. An undeclared one
# is a hidden landmine. 占位可以有，但必须当场告诉用户；偷偷埋下的占位是雷。
PLACEHOLDER_ROOTS = ["src", "services"]

# --- check 4: one version, three places -------------------------------------------------
VERSION_FILE = Path("src/_version.py")
CHANGELOG = Path("CHANGELOG.md")


def _fail(check: str, detail: str) -> str:
    print(f"  ✗ {check}\n{detail}")
    return check


def _ok(check: str) -> None:
    print(f"  ✓ {check}")


def check_orchestrator_is_generic() -> str | None:
    """The main loop must not mention any specific task. / 主循环不许提到任何具体任务。"""
    name = "orchestrator stays task-agnostic / 主循环保持任务无关"
    text = (REPO / ORCHESTRATOR).read_text(encoding="utf-8")
    hits = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for word in TASK_SPECIFIC_WORDS:
            if word in line:
                hits.append(f"      {ORCHESTRATOR}:{lineno}: {line.strip()[:90]}  ← {word!r}")
                break
    if hits:
        return _fail(name, "\n".join(hits) + "\n    → 任务专属逻辑应下沉到世界，不留在通用主循环。")
    _ok(name)
    return None


def check_no_dead_config() -> str | None:
    """Every re-exported config constant must have a consumer. / 每个配置常量都得有人用。"""
    name = "no dead config / 无死配置"
    text = (REPO / CONFIG_FILE).read_text(encoding="utf-8")
    names = re.findall(r"^([A-Z][A-Z0-9_]*)\s*=\s*_settings\.(\w+)", text, re.M)
    dead = []
    for const, field in names:
        # Note: being listed in _RUNTIME_PARAMS_SHOWN does NOT excuse a constant — that
        # path reads the lowercase *field*, so an unused constant is still dead code.
        # 注意：出现在 _RUNTIME_PARAMS_SHOWN 里**不能**豁免常量——那条路读的是小写字段，
        # 常量没人用就还是死代码。（第一版守卫在这里写错了对象，反向验证时抓出来的。）
        found = subprocess.run(
            ["grep", "-rIlw", "--include=*.py", const, *CONFIG_CONSUMERS],
            cwd=REPO, capture_output=True, text=True,
        ).stdout.split()
        if not [f for f in found if Path(f) != CONFIG_FILE]:
            dead.append(f"      {const} (field {field}) —— 定义了但全仓没人用")
    if dead:
        return _fail(name, "\n".join(dead) + "\n    → 要么接上消费方，要么连同 .env.example 一起删掉。")
    _ok(name)
    return None


def check_no_placeholders() -> str | None:
    """Placeholders must be declared, not buried. / 占位必须登记，不许偷偷埋。"""
    name = "no unregistered placeholders / 无未登记占位"
    found = subprocess.run(
        ["grep", "-rIn", "--include=*.py", "PLACEHOLDER", *PLACEHOLDER_ROOTS],
        cwd=REPO, capture_output=True, text=True,
    ).stdout.strip()
    if found:
        return _fail(name, "\n".join(f"      {ln}" for ln in found.splitlines())
                     + "\n    → 占位即登记：告诉用户 + 记进待办，别留在代码里过夜。")
    _ok(name)
    return None


def check_version_is_consistent(tag: str | None) -> str | None:
    """__version__, CHANGELOG top entry and the git tag must agree. / 三处版本号必须一致。"""
    name = "version single source / 版本号单一来源"
    ver_text = (REPO / VERSION_FILE).read_text(encoding="utf-8")
    m = re.search(r'^__version__\s*=\s*"([^"]+)"', ver_text, re.M)
    if not m:
        return _fail(name, f"      {VERSION_FILE} 里找不到 __version__")
    version = m.group(1)

    log_text = (REPO / CHANGELOG).read_text(encoding="utf-8")
    m2 = re.search(r"^##\s*\[([^\]]+)\]", log_text, re.M)
    if not m2:
        return _fail(name, f"      {CHANGELOG} 顶栏解析不出版本号")
    changelog_version = m2.group(1)

    problems = []
    if changelog_version != version:
        problems.append(f"      __version__={version}  但 CHANGELOG 顶栏={changelog_version}")
    if tag:
        if tag.lstrip("v") != version:
            problems.append(f"      git tag={tag}  但 __version__={version}")
    if problems:
        return _fail(name, "\n".join(problems)
                     + "\n    → 封版时三处一起改：src/_version.py、CHANGELOG.md、git tag。")
    _ok(name + f" ({version})")
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tag", help="git tag to check the version against (release only)")
    args = ap.parse_args(argv)

    print("ANIMA self-checks / 项目自检")
    failures = [f for f in (
        check_orchestrator_is_generic(),
        check_no_dead_config(),
        check_no_placeholders(),
        check_version_is_consistent(args.tag),
    ) if f]

    if failures:
        print(f"\n{len(failures)} check(s) failed / {len(failures)} 项不过")
        return 1
    print("\nAll checks passed / 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
