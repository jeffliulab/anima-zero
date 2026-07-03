"""多相机一等公民：契约（多命名图）在 provider 消息 / orchestrator / 会话存储 三层的行为。

对应关系的唯一约定：state["cameras"] 的名字顺序 = 图片顺序（见 awi_mcp.py / world_client.py）。
"""
from __future__ import annotations

from anima.awi import ActionResult, Capabilities, Observation, ToolSpec
from anima.llm import LLMReply
from anima.llm.base import norm_images
from anima.llm.openai_compat import _messages as oai_messages
from anima.llm.claude import _messages as claude_messages
from anima.orchestrator import Orchestrator
from anima.registry import WorldRegistry
from anima.session import SessionStore

PNG_A = b"\x89PNG-a"
PNG_B = b"\x89PNG-b"
IMAGES = [{"name": "oblique", "png": PNG_A}, {"name": "overhead", "png": PNG_B}]


def test_norm_images_shapes():
    assert norm_images(None) == []
    assert norm_images(PNG_A) == [("", PNG_A)], "单图 bytes 老形状：无名单张"
    assert norm_images(IMAGES) == [("oblique", PNG_A), ("overhead", PNG_B)]
    assert norm_images([{"name": "x", "png": None}]) == [], "空 png 不进消息"


def test_openai_messages_carry_named_images():
    msgs = oai_messages("sys", [], IMAGES)
    content = msgs[-1]["content"]
    imgs = [c for c in content if c["type"] == "image_url"]
    labels = [c["text"] for c in content if c["type"] == "text"]
    assert len(imgs) == 2, "两路相机 → 两个 image block"
    assert any("oblique" in t for t in labels) and any("overhead" in t for t in labels), \
        "每张图要带相机名标注（对应关系交给大脑）"


def test_claude_messages_carry_named_images():
    msgs = claude_messages([], IMAGES)
    content = msgs[-1]["content"]
    imgs = [c for c in content if c["type"] == "image"]
    labels = [c["text"] for c in content if c["type"] == "text"]
    assert len(imgs) == 2
    assert any("oblique" in t for t in labels) and any("overhead" in t for t in labels)


class _TwoCamWorld:
    name = "twocam"
    base = "fake://t"

    def capabilities(self):
        return Capabilities(self.name, "t", [ToolSpec("move", "动", {}, "tool")])

    def perceive(self):
        return Observation(image_png=PNG_A, state={"cameras": ["oblique", "overhead"]},
                           images=list(IMAGES))

    def invoke(self, name, *, _on_progress=None, _should_abort=None, **a):
        return ActionResult(True, "ok")


class _SpyLLM:
    vision = True
    model = "fake"

    def __init__(self):
        self.seen_image = None

    def chat(self, system, history, tools, image):
        self.seen_image = image
        return LLMReply(text="看到了")


def test_orchestrator_passes_full_image_set(tmp_path):
    world = _TwoCamWorld()
    reg = WorldRegistry()
    reg._worlds[world.name] = world
    store = SessionStore(root=str(tmp_path))
    orch = Orchestrator(reg, store)
    session, _ = store.new(world.name, "fake")
    llm = _SpyLLM()
    orch.handle(session, "看一眼", llm)
    assert llm.seen_image == IMAGES, "多相机时应把全套命名图交给 LLM（不是只给主图）"
    # 会话存储：主图 image_ref 照旧 + images 全集（名字↔ref 对应）
    per = [m for m in store.get(session.id).messages if m.get("role") == "perception"][0]
    assert per["image_ref"] and per["image_ref"].endswith("0.png")
    assert [i["name"] for i in per["images"]] == ["oblique", "overhead"]
    assert per["images"][1]["ref"].endswith("0_overhead.png")


def test_single_camera_behavior_unchanged(tmp_path):
    """单相机世界（images 只有 0/1 张）：LLM 仍收 bytes 老形状，历史记录无 images 字段。"""
    class _OneCam(_TwoCamWorld):
        def perceive(self):
            return Observation(image_png=PNG_A, state={}, images=[{"name": "", "png": PNG_A}])

    world = _OneCam()
    reg = WorldRegistry()
    reg._worlds[world.name] = world
    store = SessionStore(root=str(tmp_path))
    orch = Orchestrator(reg, store)
    session, _ = store.new(world.name, "fake")
    llm = _SpyLLM()
    orch.handle(session, "看", llm)
    assert llm.seen_image == PNG_A, "单相机：老形状 bytes，行为不变"
    per = [m for m in store.get(session.id).messages if m.get("role") == "perception"][0]
    assert "images" not in per, "单图不加 images 字段（追加不替换的兼容原则）"
