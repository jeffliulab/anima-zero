"""按配置加载**场景资产库**的内容：布局定义、机器人清单、场景 MJCF。

当前挂的是 **alice-house**（开源，MIT）——一套用代码生成的住宅，外加两台机器人和它们的策略。

为什么要单独一个模块：资产库是**外部仓库**（路径走配置、env 可覆盖），不是一个能
`import` 的包，得用 importlib 按文件路径加载。这段样板原先在 world.py、sim.py、test_walk.py
里各抄了一份——抄第三份的时候 test_walk.py 就抄错了（还写着场景外置之前的 `import scene.layout`，
从 v0.9 起一直是坏的、跑不起来，README 里却还写着它是自测）。收到一处，谁也别再抄。

⚠️ 本模块和它的配置项**故意不带资产库的名字**（用 ASSETS_ROOT 而不是 ALICE_ROOT）：
   资产库 2026-07-26 从 Domus 改名成 alice-house，那次改名之所以要动世界侧的代码，
   就是因为当初把库名写进了变量名。解耦之后，下次再改名这边一行都不用动。

用法：
    from scene_assets import layout
    L = layout()
    x, y = L.START_POS_XY
"""
from __future__ import annotations

import importlib.util
import os

import config as C

_cached = None
_robots = None


def robots():
    """资产库的机器人清单（`robots/manifest.py`）：一台机器人一条，写清模型/策略/相机/
    力矩怎么发。⛔ 这是"这台机器人是什么"的单一真相源，世界侧不许另抄一份。"""
    global _robots
    if _robots is not None:
        return _robots
    path = os.path.join(C.ASSETS_ROOT, "robots", "manifest.py")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"找不到机器人清单 {path}。它随场景资产库走（alice-house v0.3 起），"
            f"老版本没有这个文件——升级资产库，或把 HOUSENAV_ASSETS_ROOT 指到新的。")
    spec = importlib.util.spec_from_file_location("assets_robots", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _robots = mod
    return mod


def robot() -> dict:
    """当前这一版世界要用哪台机器人（`HOUSENAV_ROBOT`，默认清单里的 DEFAULT_ROBOT）。"""
    r = robots()
    return r.get(C.ROBOT or r.DEFAULT_ROBOT)


def robot_key() -> str:
    return C.ROBOT or robots().DEFAULT_ROBOT


def layout():
    """场景的 layout 模块（房间矩形 / 出生点 / 家具 / 房间归属判定）。加载一次即缓存。"""
    global _cached
    if _cached is not None:
        return _cached
    path = os.path.join(C.ASSETS_ROOT, "layout.py")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"找不到场景布局 {path}。\n"
            f"场景住在独立的资产库（默认在项目根的 alice-house/），"
            f"用 HOUSENAV_ASSETS_ROOT 指过去。")
    spec = importlib.util.spec_from_file_location("assets_layout", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _cached = mod
    return mod


def scene_xml_for(key: str) -> str:
    """某台机器人对应的场景 MJCF 的完整路径。

    **一台机器人一份场景文件**（`house-go2.xml` / `house-g1.xml`）——机器人的网格路径在编译期
    就定死了，两台塞不进同一份 MJCF。命名规则与资产库 `make_house.py` 的 `scene_filename()`
    是同一条，改名要两边一起改。
    """
    path = os.path.join(C.ASSETS_ROOT, f"house-{key}.xml")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"找不到场景 {path}。先在资产库里生成它：\n"
            f"    cd {C.ASSETS_ROOT} && python make_house.py --robot {key}")
    return path


def scene_xml() -> str:
    """当前配置那台机器人的场景路径。"""
    return scene_xml_for(robot_key())
