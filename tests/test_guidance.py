"""世界说明书 guidance（v0.4）：世界经 MCP prompt 自我介绍，大脑把它拼进系统提示。

这里钉住 orchestrator._system() 的行为：世界声明了 guidance → 系统提示里出现；没声明 → 不出现。
这是"让大脑保持纯净通用（不为某个世界写死逻辑，改由世界自述）"的决策心脏，必须有测试网。
确定性、不联网、用假世界。
"""
from __future__ import annotations

from anima.awi import ActionResult, Capabilities, Observation, ToolSpec
from anima.behavior import RunnerManager
from anima.orchestrator import Orchestrator
from anima.registry import WorldRegistry
from anima.session import SessionStore


class _World:
    name = "toy"
    base = "fake://toy"

    def __init__(self, guidance: str = ""):
        self._guidance = guidance

    def capabilities(self):
        return Capabilities(self.name, "1", [ToolSpec("ping", "原子能力", {}, "read")], guidance=self._guidance)

    def perceive(self):
        return Observation(image_png=None, state={})

    def invoke(self, name, **a):
        return ActionResult(True, "ok")


def _orch(tmp_path, world):
    reg = WorldRegistry()
    reg._worlds[world.name] = world
    return Orchestrator(reg, SessionStore(root=str(tmp_path)), runs=RunnerManager())


def test_system_prompt_includes_world_guidance(tmp_path):
    w = _World(guidance="我是玩具世界，想干活就用 ping，别乱来。")
    sys = _orch(tmp_path, w)._system(w)
    assert "说明书" in sys                 # 有"说明书"这个块
    assert "我是玩具世界，想干活就用 ping" in sys  # 世界的原话被拼进去了


def test_system_prompt_omits_block_when_no_guidance(tmp_path):
    w = _World(guidance="")               # 世界没提供说明书
    sys = _orch(tmp_path, w)._system(w)
    assert "说明书" not in sys             # 不凭空造一个块
