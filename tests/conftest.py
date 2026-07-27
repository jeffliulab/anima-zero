"""pytest 公共夹具 / 路径。

`anima` 包已可直接 import（pyproject 把 src/ 映射成 anima）。
`world/sim-chess/render.py` 是"世界"进程的渲染器、不是 anima 包的一部分，
但视觉 round-trip 测试要用它当"摄像头画面"的真实来源，所以把它所在目录加进 sys.path。
"""
from __future__ import annotations

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SIM_CHESS = os.path.join(_HERE, "..", "world", "sim-chess")
if _SIM_CHESS not in sys.path:
    sys.path.insert(0, os.path.abspath(_SIM_CHESS))


@pytest.fixture(autouse=True)
def _isolated_anima_home(tmp_path, monkeypatch):
    """Point `ANIMA_HOME` at a throwaway directory for every test.

    The trust store lives outside the repository, in the user's home — which is correct in
    production and unacceptable in a test run: a suite that writes there could approve a
    world on the developer's real machine, or read an approval they made by hand and pass
    for the wrong reason. Both are silent. Isolating it once here is cheaper than
    remembering to isolate it in each test.

    每个测试的 `ANIMA_HOME` 都指向一个用完就扔的目录。

    信任存储住在仓库之外的用户主目录里——这在生产上是对的，在测试里则不可接受：一个往那儿写的测试
    套件可能在开发者的**真实机器上批准一个世界**，也可能读到他手工批过的记录、于是**因为错误的
    原因通过**。两种都是静默的。在这里隔离一次，比每个测试都记得隔离要便宜。
    """
    monkeypatch.setenv("ANIMA_HOME", str(tmp_path / "anima-home"))
