"""世界说明书 guidance（v0.4）：世界经 MCP prompt 自我介绍，大脑把它拼进系统提示。

这里钉住 orchestrator._system() 的行为：世界声明了 guidance → 系统提示里出现；没声明 → 不出现。
这是"让大脑保持纯净通用（不为某个世界写死逻辑，改由世界自述）"的决策心脏，必须有测试网。
确定性、不联网、用假世界。
"""
from __future__ import annotations

from anima.core.awi import ActionResult, Capabilities, Observation, ToolSpec

from anima.core.orchestrator import Orchestrator
from anima.clients.registry import WorldRegistry
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
    return Orchestrator(reg, SessionStore(root=str(tmp_path)))


def test_system_prompt_includes_world_guidance(tmp_path):
    w = _World(guidance="我是玩具世界，想干活就用 ping，别乱来。")
    sys = _orch(tmp_path, w)._system(w)
    assert "说明书" in sys                 # 有"说明书"这个块
    assert "我是玩具世界，想干活就用 ping" in sys  # 世界的原话被拼进去了


def test_system_prompt_omits_block_when_no_guidance(tmp_path):
    w = _World(guidance="")               # 世界没提供说明书
    sys = _orch(tmp_path, w)._system(w)
    assert "说明书" not in sys             # 不凭空造一个块


# ---- sim-house-nav 的说明书不许泄题（v1.0 红线，Jeff 定）----
# 背景：v0.9 的说明书把十二个房间的家具逐间点名、还附了一张标志物对照表，等于替大脑做了识别；
# 而且答案喂到那个份上，四个目标房间它还是错了三个。这个世界要考的就是「自己看画面认出这是
# 哪间屋」，所以说明书里只许写「怎么跟我打交道」，不许写「屋子里有什么」。
# 这条规矩全靠自觉很容易在下次改文案时破功，所以钉一个测试。
_ANSWER_KEY_WORDS = (
    # 房间名
    "玄关", "客厅", "餐厅", "中厨", "主卧", "衣帽间", "主卫", "次卧", "客卫", "小孩房", "洗衣房",
    # 标志家具/家电
    "沙发", "灶眼", "抽油烟机", "烤箱", "洗碗机", "冰箱", "浴缸", "马桶", "床头柜", "衣柜", "餐桌",
)


def _house_nav_guidance() -> str:
    """从世界源码里取出 GUIDANCE 常量。用 ast 静态读——import 会去起 MuJoCo 仿真。"""
    import ast
    import pathlib
    src = pathlib.Path(__file__).resolve().parents[1] / "world" / "sim-house-nav" / "world.py"
    for node in ast.parse(src.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "GUIDANCE":
            return ast.literal_eval(node.value)
    raise AssertionError("world/sim-house-nav/world.py 里找不到 GUIDANCE")


def test_house_nav_guidance_has_no_answer_key():
    g = _house_nav_guidance()
    leaked = [w for w in _ANSWER_KEY_WORDS if w in g]
    assert not leaked, (
        f"说明书里出现了泄题词 {leaked}——这个世界要考的是「自己看画面认房间」，"
        f"说明书只许写怎么跟世界打交道，不许写屋子里有哪些房间、摆着什么。")


def test_house_nav_guidance_still_explains_how_to_interact():
    """瘦身不等于删光：怎么跟这个世界打交道该说的还得说（别把有用的一起砍了）。"""
    g = _house_nav_guidance()
    for must in ("前视相机", "往前走", "左转", "环视", "笔记本", "看见就算到"):
        assert must in g, f"说明书缺了「{must}」——这属于「怎么跟我打交道」，不该被瘦身砍掉"
