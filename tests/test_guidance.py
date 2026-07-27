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
    assert "description of itself" in sys   # 有「世界自述」这个块
    assert "我是玩具世界，想干活就用 ping" in sys  # 世界的原话被拼进去了


def test_system_prompt_omits_block_when_no_guidance(tmp_path):
    w = _World(guidance="")               # 世界没提供说明书
    sys = _orch(tmp_path, w)._system(w)
    assert "description of itself" not in sys   # 不凭空造一个块


# ---- sim-house-nav 的说明书不许泄题（v1.0 红线，Jeff 定）----
# 背景：v0.9 的说明书把十二个房间的家具逐间点名、还附了一张标志物对照表，等于替大脑做了识别；
# 而且答案喂到那个份上，四个目标房间它还是错了三个。这个世界要考的就是「自己看画面认出这是
# 哪间屋」，所以说明书里只许写「怎么跟我打交道」，不许写「屋子里有什么」。
# 这条规矩全靠自觉很容易在下次改文案时破功，所以钉一个测试。
# ⚠️ 中英**都要列**。v1.1 把说明书正文改成了英文，而这张表当时只有中文——
#    那一刻这条守卫就**形同虚设**了：它一个词都不会命中，测试照绿，红线其实没人守。
#    「守卫因为被守的东西换了形态而静默失效」是本项目反复踩到的同一类坑（v0.9 漏登记 awi_mcp
#    副本、v1.1 死配置豁免写错对象），所以这里把两种语言一起钉住。
_ANSWER_KEY_WORDS = (
    # 房间名
    "玄关", "客厅", "餐厅", "中厨", "主卧", "衣帽间", "主卫", "次卧", "客卫", "小孩房", "洗衣房",
    "hallway", "living room", "dining", "kitchen", "bedroom", "wardrobe", "bathroom",
    "nursery", "laundry", "en-suite",
    # 标志家具/家电
    "沙发", "灶眼", "抽油烟机", "烤箱", "洗碗机", "冰箱", "浴缸", "马桶", "床头柜", "衣柜", "餐桌",
    "sofa", "couch", "hob", "stove", "range hood", "extractor", "oven", "dishwasher",
    "fridge", "refrigerator", "bathtub", "toilet", "nightstand", "bedside", "dining table",
)


def _house_nav_module(name: str):
    """加载 sim-house-nav 的一个轻量模块（guidance / config）。

    这两个模块只依赖标准库，**故意**和 world.py / sim.py 分开——那两个一 import 就起 MuJoCo，
    大脑仓的测试跑不动。说明书之所以能被这里检查，就是因为它住在独立的 guidance.py 里。
    """
    import importlib.util
    import pathlib
    import sys
    d = pathlib.Path(__file__).resolve().parents[1] / "world" / "sim-house-nav"
    sys.path.insert(0, str(d))          # guidance.py 要 import config
    try:
        spec = importlib.util.spec_from_file_location(f"housenav_{name}", d / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.path.remove(str(d))


def _house_nav_guidance() -> str:
    return _house_nav_module("guidance").GUIDANCE


def test_house_nav_guidance_has_no_answer_key():
    g = _house_nav_guidance()
    leaked = [w for w in _ANSWER_KEY_WORDS if w in g]
    assert not leaked, (
        f"说明书里出现了泄题词 {leaked}——这个世界要考的是「自己看画面认房间」，"
        f"说明书只许写怎么跟世界打交道，不许写屋子里有哪些房间、摆着什么。")


def test_house_nav_guidance_still_explains_how_to_interact():
    """瘦身不等于删光：怎么跟这个世界打交道该说的还得说（别把有用的一起砍了）。"""
    g = _house_nav_guidance()
    # ⚠️ 这里**不列环视**：它是可开关的能力（v1.0 默认关），在不在说明书里由开关决定，
    #    由下面那条 test_..._action_count_matches_switch 管。这里只列"永远该有"的。
    # 说明书正文自 v1.1 起是英文（模型读的东西只有一个版本，见大脑仓 src/prompts.py），
    # 所以这里断言的是**同样这几件事的英文说法**——守的东西一个没变。
    for must in ("forward-facing camera", "walk forward", "turn left", "notebook",
                 "seeing it is enough", "clearance_m"):
        assert must in g, f"说明书缺了「{must}」——这属于「怎么跟我打交道」，不该被瘦身砍掉"


def test_house_nav_guidance_action_count_matches_switch():
    """说明书说的动作数，必须和**实际注册的工具数**对得上。

    ⛔ "声称有而实际没有" 是本项目明令禁止的一类硬编码。v1.0 把环视默认关掉了，
    说明书要是还写着"四个动作，其中环视…"，大脑就会去调一个工具单上没有的东西。
    """
    g = _house_nav_guidance()
    cfg = _house_nav_module("config")
    if cfg.LOOK_AROUND:
        assert "Four actions" in g and "look around" in g
    else:
        assert "Three actions" in g, "环视关着，说明书就该说三个动作"
        assert "look around" not in g, "环视关着，说明书里不该再提它——大脑会去调一个不存在的工具"
