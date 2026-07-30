"""Does the conformance checker actually fail on a broken world?

一致性检查器在世界坏掉时，真的会红吗？

⛔ Why this file is not optional. A checker that only ever reports success is worse than no
checker: it hands out a green tick that means nothing, and people rely on it. This project
has already caught three guards that had silently stopped guarding, and every one of them
was green the whole time. So every check in `conformance.py` is exercised here against input
that should fail it.

⛔ 为什么这个文件不是可选的。一个只会报成功的检查器**比没有检查器更糟**：它发出一个毫无意义的绿勾，
而人会依赖它。这个项目已经抓到过三条悄悄停止守卫的守卫，且它们**自始至终都是绿的**。
所以 `conformance.py` 里的每一条检查，这里都用"本该让它红"的输入过一遍。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from anima import conformance
from anima.conformance import FAIL, PASS, WARN, Report


# ---------------------------------------------------------------- fakes
# Stand-ins for what the MCP SDK hands back. Only the attributes the checker reads.
# 冒充 MCP SDK 的返回。只带检查器真正会读的那几个属性。

@dataclass
class FakeAnnotations:
    readOnlyHint: bool | None = None


@dataclass
class FakeTool:
    name: str
    description: str | None = "does a thing"
    inputSchema: dict | None = None
    annotations: Any = None

    def __post_init__(self):
        if self.inputSchema is None:
            self.inputSchema = {"type": "object", "properties": {}}


@dataclass
class FakeText:
    text: str


@dataclass
class FakeBlob:
    blob: bytes = b"\x89PNG"
    mimeType: str = "image/png"


def _statuses(rep: Report, rule: str | None = None) -> list[str]:
    return [c.status for c in rep.checks if rule is None or c.rule == rule]


def _fails(rep: Report) -> list[str]:
    return [c.title for c in rep.failures]


# ---------------------------------------------------------------- §3.1 tools

def test_tool_with_non_object_schema_fails():
    """Tool arguments are named, so the schema has to be an object schema.
    / 工具参数是有名字的，所以 schema 必须是 object 型。"""
    rep = Report(url="x")
    conformance._check_tools(rep, [FakeTool("move", inputSchema={"type": "array"})])
    assert any("not an object schema" in t for t in _fails(rep))


def test_tool_with_object_schema_passes():
    rep = Report(url="x")
    conformance._check_tools(rep, [FakeTool("move")])
    assert not rep.failures


def test_unnamed_tool_fails():
    rep = Report(url="x")
    conformance._check_tools(rep, [FakeTool("")])
    assert any("empty name" in t for t in _fails(rep))


def test_missing_description_warns_but_does_not_fail():
    """A description-less tool is unhelpful, not non-conformant. Blurring the two would make
    the distinction worthless. / 没描述的工具是不好用，不是违规。混为一谈，这个区分就白做了。"""
    rep = Report(url="x")
    conformance._check_tools(rep, [FakeTool("move", description="")])
    assert not rep.failures
    assert any(c.status == WARN and "no description" in c.title for c in rep.checks)


def test_overlong_description_warns():
    rep = Report(url="x")
    conformance._check_tools(rep, [FakeTool("move", description="x" * 100_000)])
    assert any(c.status == WARN and "exceeds the host's cap" in c.title for c in rep.checks)


def test_missing_readonlyhint_warns():
    rep = Report(url="x")
    conformance._check_tools(rep, [FakeTool("move", annotations=None)])
    assert any(c.status == WARN and "readOnlyHint" in c.title for c in rep.checks)
    rep2 = Report(url="x")
    conformance._check_tools(rep2, [FakeTool("m", annotations=FakeAnnotations(readOnlyHint=True))])
    assert not any("readOnlyHint" in c.title for c in rep2.checks)


# ---------------------------------------------------------------- §3.2 observation

def test_empty_observation_fails():
    rep = Report(url="x")
    conformance._check_observation(rep, [])
    assert any("returned nothing" in t for t in _fails(rep))


def test_state_that_is_not_json_fails():
    rep = Report(url="x")
    conformance._check_observation(rep, [FakeText("{not json")])
    assert any("not valid JSON" in t for t in _fails(rep))


def test_state_that_is_a_list_fails():
    """A bare list has no contract — state is a mapping of named readings.
    / 一个裸列表没有契约——state 是"有名字的读数"的映射。"""
    rep = Report(url="x")
    conformance._check_observation(rep, [FakeText(json.dumps([1, 2, 3]))])
    assert any("not an object" in t for t in _fails(rep))


def test_image_that_is_not_png_fails():
    rep = Report(url="x")
    conformance._check_observation(rep, [FakeText("{}"), FakeBlob(mimeType="image/jpeg")])
    assert any("not image/png" in t for t in _fails(rep))


def test_empty_state_is_allowed():
    """sim-chess deliberately gives `{}` — no ground truth of any kind. That is the point of
    that world, not a defect. / sim-chess 有意只给 `{}`，一点真值都不给。那是那个世界的**用意**，
    不是缺陷。"""
    rep = Report(url="x")
    conformance._check_observation(rep, [FakeText("{}")])
    assert not rep.failures


def test_no_image_warns_but_is_allowed():
    rep = Report(url="x")
    conformance._check_observation(rep, [FakeText("{}")])
    assert any(c.status == WARN and "No image" in c.title for c in rep.checks)


# ⭐ The check that matters most: blobs carry no names, so their order is the only thing tying
# a picture to a camera. A mismatch is silent in every other part of the system.
# ⭐ 最要紧的那条：blob 不带名字，所以**顺序**是画面与相机之间唯一的联系。对不上的时候，
# 系统的其它任何地方都不会吭一声。

def test_camera_count_mismatch_fails():
    rep = Report(url="x")
    conformance._check_observation(
        rep, [FakeText(json.dumps({"cameras": ["head", "chase"]})), FakeBlob()])
    assert any("does not match the number of images" in t for t in _fails(rep))


def test_camera_count_match_passes():
    rep = Report(url="x")
    conformance._check_observation(
        rep, [FakeText(json.dumps({"cameras": ["head", "chase"]})), FakeBlob(), FakeBlob()])
    assert not rep.failures


# ---------------------------------------------------------------- §3.3 guidance

def test_missing_guidance_warns_not_fails():
    rep = Report(url="x")
    conformance._check_guidance(rep, "")
    assert not rep.failures
    assert any(c.status == WARN for c in rep.checks)


def test_overlong_guidance_warns():
    rep = Report(url="x")
    conformance._check_guidance(rep, "x" * 100_000)
    assert any(c.status == WARN and "exceeds the host's cap" in c.title for c in rep.checks)


def test_normal_guidance_passes():
    rep = Report(url="x")
    conformance._check_guidance(rep, "You are looking at a desk with a pen on it.")
    assert _statuses(rep) == [PASS]


# ---------------------------------------------------------------- §3.4 config

def test_config_without_options_fails():
    rep = Report(url="x")
    conformance._check_config(rep, {"robot": "go2"})
    assert any("no `options` list" in t for t in _fails(rep))


def test_config_option_without_key_fails():
    rep = Report(url="x")
    conformance._check_config(rep, {"options": [{"label": "Robot"}]})
    assert any("has no `key`" in t for t in _fails(rep))


def test_absent_config_is_fine():
    rep = Report(url="x")
    conformance._check_config(rep, None)
    assert _statuses(rep) == [PASS]


# ---------------------------------------------------------------- report

def test_report_is_not_conformant_when_anything_failed():
    rep = Report(url="x")
    rep.add(PASS, "1", "fine")
    assert rep.conformant
    rep.add(FAIL, "2", "broken")
    assert not rep.conformant


def test_report_stays_conformant_with_only_warnings():
    rep = Report(url="x")
    rep.add(WARN, "1", "could be better")
    assert rep.conformant


def test_formatted_report_always_states_what_it_did_not_check():
    """⛔ A green report read as "this world is safe" is worse than no report. The limits are
    printed every time, including when everything passed.
    / ⛔ 一份被读成"这个世界安全"的绿报告比没有报告更糟。局限每次都印，全过的时候也印。"""
    rep = Report(url="x")
    rep.add(PASS, "1", "fine")
    out = conformance.format_report(rep)
    assert "What this did not check" in out
    assert "god's-eye" in out
    assert "at approval time" in out


def test_unreachable_world_reports_rather_than_raising():
    """A world that is not there is a report, not a traceback — this command is aimed at
    people debugging their own world. / 世界不在，应该给一份报告而不是一段 traceback——
    这条命令的使用者正是在调自己那个世界的人。"""
    rep = conformance.run("http://127.0.0.1:1", timeout=1.0)
    assert not rep.conformant
    assert any("MCP handshake" in t for t in _fails(rep))


# 端到端（起一个真世界、跑完整条管道）在 tests/test_awi_minimal_world.py。
# 它自带靶子，不连仓里任何一个具体世界——用户完全可以只装 anima、自己写世界。
# 这个文件只做单元测试：喂坏输入给每个 _check_*，证明**不合规的世界会被判红**。
