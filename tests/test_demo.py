"""`anima demo` 与它的示例世界：「装完就能跑」这条承诺的守卫。

示例世界（src/examples/minimal_world.py）随 wheel 分发，是给用户照抄的模板。
这里守三件事：它真过自家 conformance（教科书第一页不能是错的）、它的两个工具各司其职
（look 只读 / step 真动 / 墙如实拒绝）、demo 命令的表面没烂（参数解析、大脑登记表）。
"""
from __future__ import annotations

from anima import cli, conformance
from anima.examples.minimal_world import CorridorWorld, serve_in_thread
from anima.llm.factory import _registry


def test_the_example_world_passes_conformance():
    """随包的示例世界必须过自家的一致性检查——它是用户照抄的模板，它不合规等于
    教科书第一页就是错的。"""
    with serve_in_thread() as base:
        rep = conformance.run(base)
    assert rep.conformant, \
        f"the shipped example world was rejected: {[c.title for c in rep.failures]}"
    assert set(rep.tool_names) == {"look", "step"}


def test_look_describes_without_touching_and_step_moves():
    """look 是眼睛（只读），step 是腿（真动）——mock/谨慎的大脑敢用前者，决策归后者。"""
    world = CorridorWorld()
    _, before = world.observe()
    report = world.look()
    _, after = world.observe()
    assert before == after, "look 改了世界，它就不再是『只读』了"
    assert "lit cell" in report

    ok, _ = world.step("right")
    _, moved = world.observe()
    assert ok and moved != before

    # 一路向左到墙，墙必须如实拒绝（不许悄悄当成功）
    for _ in range(10):
        ok, msg = world.step("left")
    assert not ok and "wall" in msg


def test_demo_command_parses_with_documented_defaults():
    args = cli.build_parser().parse_args(["demo"])
    assert args.fn is cli.cmd_demo
    assert args.brain is None and args.say == cli.DEMO_SAY


def test_the_demo_brain_is_registered_without_eyes():
    """demo 脑在登记表里、走 Ollama、vision=False（纯文本 4B；主循环据此不喂图）。"""
    reg = _registry()
    assert "demo" in reg, "demo 脑没了——anima demo 的默认路径就断了"
    assert reg["demo"]["hosting"] == "local"
    llm = reg["demo"]["build"]()
    assert llm.vision is False


def test_mock_brain_is_still_there_as_the_last_resort():
    """T0：加 demo 脑不许挤掉 mock——它是「一个 key 都没有」的人最后的兜底。"""
    assert "mock" in _registry()
