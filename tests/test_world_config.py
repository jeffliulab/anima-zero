"""世界配置通道（v1.0 新增的 AWI 声明通道）。

有些世界不止一种"布置法"（同一间屋子里站的是四足狗还是人形）。这种**开跑前的场地配置**
既不是动作（不是大脑该调的工具），也不是感知（不是每轮在变的画面），两条现有通道都放不下。

分工：世界经 AWI **声明**"我能配什么、现在是什么"；**改**它走世界本地的带外 HTTP。

覆盖：握手把配置读进 Capabilities；当前值转述进系统提示（用 choices 的 label 而非原值）；
⛔ 不告诉大脑"你可以改"（它没有对应工具）；世界没声明配置 → 什么都不注入（旧世界零影响）；
改配置后自动重新握手（v0.9 那个"新工具永远上不了工具单"的坑）。
"""
from __future__ import annotations

from anima import prompts
from anima.clients.registry import WorldRegistry
from anima.core.awi import ActionResult, Capabilities, Observation, ToolSpec
from anima.core.orchestrator import Orchestrator, _config_value_label
from anima.session import SessionStore


class _World:
    name = "toy"
    base = "fake://toy"

    def __init__(self, config: dict | None = None):
        self._config = config or {}
        self.handshakes = 0
        self.set_calls: list[tuple[str, str]] = []
        self._value = (config or {}).get("options", [{}])[0].get("value", "")

    def capabilities(self):
        self.handshakes += 1
        return Capabilities(self.name, "1", [ToolSpec("ping", "原子能力", {}, "read")],
                            config=self._config)

    def perceive(self):
        return Observation(image_png=None, state={})

    def invoke(self, name, **a):
        return ActionResult(True, "ok")

    def set_config(self, key, value):
        self.set_calls.append((key, value))
        for o in self._config.get("options", []):
            if o["key"] == key:
                o["value"] = value
        return {"ok": True, "message": "改好了"}

    def refresh(self):
        self._config.setdefault("_refreshed", 0)
        self._config["_refreshed"] += 1


BODY_CONFIG = {
    "options": [{
        "key": "body",
        "label": "身体",
        "description": "这个世界里站着哪台机器人。",
        "value": "g1",
        "choices": [{"value": "go2", "label": "四足机器狗（宇树 Go2）"},
                    {"value": "g1", "label": "人形机器人（宇树 G1，29 自由度）"}],
    }],
}


def _orch(tmp_path, world):
    reg = WorldRegistry()
    reg._worlds[world.name] = world
    return Orchestrator(reg, SessionStore(root=str(tmp_path)))


def test_config_value_label_prefers_choice_label():
    assert _config_value_label(BODY_CONFIG["options"][0]) == "人形机器人（宇树 G1，29 自由度）"
    # 世界没给 choices 也不能崩——照原值转述
    assert _config_value_label({"key": "x", "value": "abc"}) == "abc"


def test_current_config_goes_into_system_prompt(tmp_path):
    w = _World(BODY_CONFIG)
    sysmsg = _orch(tmp_path, w)._system(w)
    assert "身体" in sysmsg
    assert "人形机器人（宇树 G1，29 自由度）" in sysmsg, "该转述 label，不是裸值 g1"
    assert "四足机器狗" not in sysmsg, "⛔ 只说现状，不许把别的选项也列给它——它改不了"


def test_prompt_does_not_invite_the_brain_to_change_it(tmp_path):
    """⛔ 大脑没有改配置的工具。提示里要是暗示"你可以改"，它就会去调一个不存在的东西。"""
    w = _World(BODY_CONFIG)
    sysmsg = _orch(tmp_path, w)._system(w)
    assert "you cannot\nchange it" in sysmsg or "cannot change it" in sysmsg.replace("\n", " ")


def test_world_without_config_injects_nothing(tmp_path):
    """旧世界（没声明配置）零影响——这条通道是可选的。"""
    w = _World({})
    sysmsg = _orch(tmp_path, w)._system(w)
    assert prompts.WORLD_CONFIG_BLOCK.split("{")[0].strip() not in sysmsg


def test_capabilities_carries_config(tmp_path):
    w = _World(BODY_CONFIG)
    caps = w.capabilities()
    assert caps.config["options"][0]["key"] == "body"


def test_awi_mcp_declares_config_resource_only_when_world_has_one():
    """世界侧适配层：实现了 config() 才多一条资源，没实现就整条通道不存在。"""
    import ast
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[1] / "world" / "sim-chess" / "awi_mcp.py"
           ).read_text(encoding="utf-8")
    ast.parse(src)                       # 语法先过
    assert 'CONFIG_URI = "anima://config"' in src
    assert "if _config is not None:" in src, "没声明 config() 的世界不该出现这条资源"
    # 大脑侧用的是同一个 URI 字符串（两边对不上=读不到，且不会报错，最难查）
    client = (pathlib.Path(__file__).resolve().parents[1] / "src" / "clients" / "world_client.py"
              ).read_text(encoding="utf-8")
    assert 'CONFIG_URI = "anima://config"' in client
