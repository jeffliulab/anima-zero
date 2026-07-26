"""第三视角跟拍的红线：**ANIMA 绝对看不到这一路**（v1.0）。

为什么值得单独一个测试文件：这一路是个上帝视角——从斜后上方看着机器人在屋里走。
一旦它漏进 `observe()`，这个世界要考的能力（自己看画面认出身在哪间屋）就直接被送掉了，
而且**不会报错、不会崩**，只会让实验结果虚高——最难发现的那种坏法。

红线在三处落实，这里逐条钉：
  ① 世界的 `observe()` 只碰头部相机那一路，代码里根本没有第三视角的影子；
  ② `/streams` 给每一路标 `awi`，第三视角标 false（网页据此分两块显示）；
  ③ 网页按 `awi` 分组，两块各有各的标题——把跟拍摆在「ANIMA 看到的画面」底下就是撒谎。

用静态检查而不是起仿真：这几条都是"代码里有没有这段"的事实，而起一次 MuJoCo 要几十秒、
还得世界侧那套 venv。世界侧另有 `test_lidar.py` 在活体上核 `observe()` 的键。
"""
from __future__ import annotations

import ast
import pathlib

WORLD_DIR = pathlib.Path(__file__).resolve().parents[1] / "world" / "sim-house-nav"
FRONTEND = pathlib.Path(__file__).resolve().parents[1] / "frontend" / "components" / "SensingArea.tsx"


def _observe_source() -> str:
    """把 world.py 里 observe() 那个函数的源码单独抠出来。"""
    src = (WORLD_DIR / "world.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "observe":
            return ast.get_source_segment(src, node) or ""
    raise AssertionError("world/sim-house-nav/world.py 里找不到 observe()")


def test_observe_never_touches_third_person():
    """① 感知函数里不许出现任何第三视角的东西。"""
    body = _observe_source()
    for banned in ("third", "chase", "第三视角"):
        assert banned not in body.lower() if banned.isascii() else banned not in body, (
            f"observe() 里出现了「{banned}」——第三视角是上帝视角，"
            f"漏进感知会让这个世界要考的能力直接失效，而且不报错。")


def test_third_person_is_only_a_stream():
    """第三视角只能经直播端点出去，不能有别的出口。"""
    sim = (WORLD_DIR / "sim.py").read_text(encoding="utf-8")
    server = (WORLD_DIR / "server.py").read_text(encoding="utf-8")
    assert "def third_person_jpeg" in sim, "第三视角的取帧函数应该在 sim.py"
    assert "/stream/third" in server, "第三视角应该有自己的直播端点"
    # 取帧函数只被直播端点用；世界对象（AWI 那一层）不该碰它
    world = (WORLD_DIR / "world.py").read_text(encoding="utf-8")
    assert "third_person_jpeg" not in world, (
        "world.py（AWI 层）不该碰第三视角——它只走 server.py 的直播端点")


def test_streams_marks_awi_visibility():
    """② /streams 每一路都要标明大脑看不看得见，且第三视角标 false。"""
    server = (WORLD_DIR / "server.py").read_text(encoding="utf-8")
    assert '"awi": True' in server, "头部相机那一路要标 awi=true"
    assert '"awi": False' in server, "第三视角那一路必须标 awi=false"


def test_frontend_splits_by_awi_flag():
    """③ 网页按 awi 分两块，且旁观那块的标题写明 ANIMA 看不到。"""
    tsx = FRONTEND.read_text(encoding="utf-8")
    assert "c.awi" in tsx, "前端要按 awi 字段分组"
    assert "ANIMA 看不到" in tsx, "旁观那一块的标题必须写明 ANIMA 看不到"
    # 向后兼容：老世界的 /streams 没有 awi 字段，得按"大脑看得见"处理
    assert "c.awi !== false" in tsx, "awi 没写时要默认 true（老世界零改动）"
