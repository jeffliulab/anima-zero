"""pytest 公共夹具 / 路径。

`anima` 包已可直接 import（pyproject 把 src/ 映射成 anima）。
`world/sim-chess/render.py` 是"世界"进程的渲染器、不是 anima 包的一部分，
但视觉 round-trip 测试要用它当"摄像头画面"的真实来源，所以把它所在目录加进 sys.path。
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SIM_CHESS = os.path.join(_HERE, "..", "world", "sim-chess")
if _SIM_CHESS not in sys.path:
    sys.path.insert(0, os.path.abspath(_SIM_CHESS))
