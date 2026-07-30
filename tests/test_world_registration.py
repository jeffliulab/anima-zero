"""接一个新世界，几处「全集」有没有都追加到（T0 红线的机器守卫）。

⛔ 背景：改「全集」类的东西——世界清单、`.env.example`、防漂移守卫的名单、启动命令——
**永远是追加，绝不是替换**。2026-06-28 真踩过：加 sim-chess 时那一行写成了只有 sim-chess，
把当时已有的那个世界从世界下拉和 AWI 页里整个挤没了；代码本身没坏，
是"全集被替换而非追加"。

光靠文档和自觉会漏（v0.9 加 sim-house-nav 时就漏登记了防漂移守卫）。这里逐处机器核对：
一个世界只要进了 `config.worlds()`，它就得在**每一处全集**里都有。

接世界的完整说明见 `world/README.md`。
"""
from __future__ import annotations

import pathlib

from anima import config

ROOT = pathlib.Path(__file__).resolve().parents[1]
ENV_EXAMPLE = ROOT / ".env.example"
RUN_DOC = ROOT.parent / "anima-zero-个人用详细开发日志" / "运行命令.md"

# 不住在本仓的世界（各自独立仓/子模块），本文件只核"清单里有没有它"，不核目录。
EXTERNAL_WORLDS = {"gazebo-chess"}   # 2026-07-08 迁去 soma-zero/sim/


def _declared_worlds() -> list[str]:
    return [name for name, _url in config.worlds()]


def test_every_world_has_a_dir_or_is_external():
    """清单里的世界要么在 world/ 下有目录，要么明确登记为外部世界。"""
    for name in _declared_worlds():
        if name in EXTERNAL_WORLDS:
            continue
        assert (ROOT / "world" / name).is_dir(), (
            f"世界「{name}」在 config.worlds() 里，但 world/{name}/ 不存在。"
            f"外部世界登记进 EXTERNAL_WORLDS，别让它静默缺席。")


def test_every_world_is_in_env_example():
    """⛔ 全集：`.env.example` 的 ANIMA_WORLDS 必须含每一个世界（追加不替换）。"""
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    line = next((ln for ln in text.splitlines() if ln.startswith("ANIMA_WORLDS=")), "")
    assert line, ".env.example 里找不到 ANIMA_WORLDS"
    for name in _declared_worlds():
        assert f"{name}=" in line, (
            f"世界「{name}」不在 .env.example 的 ANIMA_WORLDS 里——"
            f"⛔ 这一行是全集，加世界要【追加】。谁替换了它，谁就把别的世界挤没了。")


def test_every_local_world_is_guarded_against_awi_drift():
    """⛔ 全集：本仓每个世界的 awi_mcp.py 都要进防漂移守卫的名单。

    v0.9 加 sim-house-nav 时漏了这一处——当时五份副本其实没漂，
    但"守卫没覆盖到"正是守卫会失效的方式：它一直绿，而它守的东西根本没被看着。
    """
    # Imported rather than text-scraped. The previous version split the guard's source on
    # the literal string "WORLDS = ", so renaming that variable made this test fail for a
    # reason that had nothing to do with what it guards.
    # 改成 import 而不是抠文本。上一版是把守卫的源码按字面量 "WORLDS = " 切开的，
    # 于是那个变量一改名，这条测试就会因为**和它守的东西毫无关系的原因**变红。
    from test_awi_mcp_copies import COPIES
    listed = {path.parent.name for path in COPIES.values()}
    for name in _declared_worlds():
        if name in EXTERNAL_WORLDS:
            continue
        if not (ROOT / "world" / name / "awi_mcp.py").exists():
            continue          # 没有这份副本的世界（如尚未实现的占位）不强求
        assert name in listed, (
            f"世界「{name}」有自己的 awi_mcp.py 副本，却不在 test_awi_mcp_copies.py 的 WORLDS 里——"
            f"它的一致性没人守着，改 AWI 协议时会静默漂移。")


def test_every_world_serves_health():
    """每个本仓世界都得有 /health：网页的在线小圆点靠它，没有就永远显示离线。"""
    for name in _declared_worlds():
        if name in EXTERNAL_WORLDS:
            continue
        server = ROOT / "world" / name / "server.py"
        if not server.exists():
            continue          # 占位世界（如 computer 只有 README）跳过
        assert "/health" in server.read_text(encoding="utf-8"), (
            f"世界「{name}」的 server.py 里没有 /health——网页会一直把它显示成离线。")


def test_multi_stream_worlds_mark_awi_visibility():
    """⛔ 有多路直播的世界，必须给每一路标明大脑看不看得见。

    不标的话，只给人看的旁观画面会被摆在网页「ANIMA 看到的画面」标题底下——**那是撒谎**，
    看的人会以为大脑也有那个上帝视角。契约与理由见 world/README.md。
    （`awi` 不写按 true 处理，所以单路世界零改动；这里只查真的有多路的。）
    """
    for name in _declared_worlds():
        if name in EXTERNAL_WORLDS:
            continue
        server = ROOT / "world" / name / "server.py"
        if not server.exists():
            continue
        src = server.read_text(encoding="utf-8")
        if '@app.get("/streams")' not in src:
            continue
        block = src.split('@app.get("/streams")')[1].split("@app.")[0]
        n_entries = block.count('"url"')
        if n_entries <= 1:
            continue          # 单路，不写 awi 也没有歧义
        assert '"awi"' in block, (
            f"世界「{name}」的 /streams 有 {n_entries} 路画面却没标 awi——"
            f"网页分不出哪一路大脑看得见。见 world/README.md 的「/streams 的 awi 字段」。")


def test_run_doc_mentions_every_world():
    """启动命令文档里要有每个世界（v0.3 漏补过 camera 的运行命令，封版才发现）。

    这份文档在本仓之外（个人开发日志），不在就跳过——它不该阻断公开仓的测试。
    """
    if not RUN_DOC.exists():
        return
    text = RUN_DOC.read_text(encoding="utf-8")
    missing = [n for n in _declared_worlds() if n not in text]
    assert not missing, f"这些世界在启动命令文档里找不到：{missing}"
