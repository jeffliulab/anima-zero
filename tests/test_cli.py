"""The command line — the part of the project a new user meets first.

A CLI rots faster than anything else in a codebase: it has no callers inside the project,
so nothing breaks when it breaks. These tests are the callers.

They stay away from anything that needs a live world or a model provider; what they hold is
the surface — that every command exists, that the flags are the ones documented, and that
the two decisions with consequences (approving a world, revoking one) do what they say.

命令行——新用户最先遇到的那部分。

CLI 比代码库里任何东西都烂得快：它在项目内部没有调用方，所以它坏了也不会有东西跟着坏。
**这些测试就是它的调用方。**

它们避开一切需要活着的世界或模型服务商的东西；它们守的是**表面**——每条命令都在、参数就是文档里写的
那些、以及那两个有后果的决定（批准一个世界、撤销一个世界）确实做了它们说的事。
"""
from __future__ import annotations

import pytest

from anima import cli
from anima.core import trust
from anima.core.awi import ToolSpec


def _parse(argv):
    return cli.build_parser().parse_args(argv)


# ================================================================== surface / 表面 ===

def test_every_documented_command_exists():
    """⛔ The set of commands, asserted as a whole. Dropping one is the kind of change that
    passes review because the diff looks like a tidy-up.
    / ⛔ 命令的**全集**，整体断言。删掉一个正是那种"diff 看起来像是在整理"、于是评审就放过去的改动。"""
    for argv in (["demo"], ["chat"], ["run", "--say", "hi"], ["serve"], ["doctor"],
                 ["world", "list"], ["world", "add", "x", "http://x"],
                 ["world", "show", "x"], ["world", "remove", "x"]):
        assert _parse(argv).fn is not None, f"命令没了：{' '.join(argv)}"


def test_serve_binds_to_this_machine_only_by_default():
    """⛔ A world does things. Serving the API to the whole network by default would let
    anyone nearby drive whatever you have connected.
    / ⛔ 世界是会**动东西**的。默认把 API 开给整个网络，等于让附近任何人都能驱动你连着的东西。"""
    assert _parse(["serve"]).host == "127.0.0.1"


def test_demo_needs_no_key():
    """The whole point of `demo`: it must work before the user has any provider account.
    / `demo` 的全部意义：它必须在用户还没有任何服务商账号时就能用。"""
    assert _parse(["demo"]).brain == "mock"


def test_run_can_continue_an_existing_session():
    assert _parse(["run", "--say", "hi", "--session", "s_1"]).session == "s_1"


def test_world_add_requires_both_a_name_and_an_address():
    with pytest.raises(SystemExit):
        _parse(["world", "add", "onlyname"])


# ================================================== the decisions with consequences ===

class _FakeWorld:
    """Stands in for a live world. `world add` reaches the network in two places — health
    and the handshake — and both are replaced here.
    / 冒充一个活着的世界。`world add` 有两处会碰网络（探活和握手），这里都替掉。"""

    def __init__(self, name="w", base="http://w"):
        self.name, self.base = name, base
        self.approved = False

    def raw_capabilities(self):
        from anima.core.awi import Capabilities
        return Capabilities(self.name, "1", [ToolSpec("wipe", "Clear everything.",
                                                      {"type": "object"}, "tool")],
                            guidance="I am a world.")

    def approve(self, store=None):
        self.approved = True
        return "hash"


@pytest.fixture
def _fake_add(monkeypatch):
    world = _FakeWorld()
    monkeypatch.setattr(cli, "_wait_for_health", lambda url, timeout: True)
    monkeypatch.setattr("anima.clients.world_client.RemoteWorld",
                        lambda name, url: world)
    return world


def test_world_add_shows_the_manifest_and_stops_when_you_say_no(_fake_add, monkeypatch, capsys):
    """⛔ The guarantee: no answer means no approval. An approval flow that proceeds on
    silence is not an approval flow.
    / ⛔ 守的是：不回答 = 不批准。一个"沉默即通过"的审批流程，不是审批流程。"""
    monkeypatch.setattr("builtins.input", lambda *_: "")
    rc = cli.cmd_world_add(_parse(["world", "add", "w", "http://w"]))

    out = capsys.readouterr().out
    assert "Clear everything." in out, "工具描述必须摊给人看"
    assert "I am a world." in out, "说明书必须**全文**摊给人看"
    assert "系统提示词" in out, "得说清批准之后这些字会去哪"
    assert rc != 0 and not _fake_add.approved


def test_world_add_approves_when_you_say_yes(_fake_add, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_: "y")
    assert cli.cmd_world_add(_parse(["world", "add", "w", "http://w"])) == 0
    assert _fake_add.approved


def test_world_add_yes_flag_is_marked_as_the_dangerous_one():
    """`--yes` skips the review. It exists for scripts, and the help text has to say that
    it is not the normal path. / `--yes` 跳过审阅。它是给脚本用的，帮助文字必须说明它不是常规路径。"""
    action = next(a for a in cli.build_parser()._subparsers._group_actions)
    add = action.choices["world"]._subparsers._group_actions[0].choices["add"]
    help_text = next(a.help for a in add._actions if a.dest == "yes")
    assert "⚠" in help_text and ("别用" in help_text or "脚本" in help_text)


def test_world_remove_revokes_by_url(tmp_path, monkeypatch):
    store = trust.TrustStore()
    store.approve("http://w", [ToolSpec("t", "d", {}, "tool")], "g")
    assert store.check("http://w", [ToolSpec("t", "d", {}, "tool")], "g").allowed

    assert cli.cmd_world_remove(_parse(["world", "remove", "http://w"])) == 0
    assert trust.TrustStore().check("http://w", [ToolSpec("t", "d", {}, "tool")], "g").state \
        == trust.UNKNOWN


def test_doctor_runs_without_anything_configured(capsys, monkeypatch):
    """`doctor` is what someone runs when nothing works. It must not itself be one of the
    things that does not work. / `doctor` 是"什么都不工作时才会去跑"的东西。
    它自己绝不能是不工作的那些东西之一。"""
    monkeypatch.setattr(cli.config, "worlds", lambda: [])
    assert cli.cmd_doctor(_parse(["doctor"])) == 0
    out = capsys.readouterr().out
    assert "mock" in out, "没配 key 的人也得看到有一个能用的大脑"
    assert "anima demo" in out, "得告诉他下一步能跑什么"
