"""按配置加载 Domus 场景的布局定义（`layout.py`）。

为什么要单独一个模块：场景住在**外部资产库 Domus**（路径走配置、env 可覆盖），不是一个能
`import` 的包，得用 importlib 按文件路径加载。这段样板原先在 world.py、sim.py、test_walk.py
里各抄了一份——抄第三份的时候 test_walk.py 就抄错了（还写着场景外置之前的 `import scene.layout`，
从 v0.9 起一直是坏的、跑不起来，README 里却还写着它是自测）。收到一处，谁也别再抄。

用法：
    from domus_scene import layout
    L = layout()
    x, y = L.START_POS_XY
"""
from __future__ import annotations

import importlib.util
import os

import config as C

_cached = None


def layout():
    """Domus 场景的 layout 模块（房间矩形 / 出生点 / 家具 / 房间归属判定）。加载一次即缓存。"""
    global _cached
    if _cached is not None:
        return _cached
    path = os.path.join(C.DOMUS_ROOT, C.DOMUS_SCENE, "layout.py")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"找不到场景布局 {path}。\n"
            f"场景住在独立资产库 Domus（默认在项目根的 domus/），"
            f"用 HOUSENAV_DOMUS_ROOT / HOUSENAV_DOMUS_SCENE 指过去。")
    spec = importlib.util.spec_from_file_location("domus_layout", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _cached = mod
    return mod


def scene_xml() -> str:
    """场景 MJCF（house.xml）的完整路径。"""
    return os.path.join(C.DOMUS_ROOT, C.DOMUS_SCENE, "house.xml")
