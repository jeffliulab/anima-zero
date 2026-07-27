"""各 awi_mcp.py 副本的防漂移守卫。

世界是独立进程/各自 venv、不共享 import，所以每个世界目录各存一份 awi_mcp.py 拷贝；
协议改动必须各处同步（文件头就写着这条约定）。以前只靠自觉，这里字节级核对——
谁改了一份忘了同步另几份，这个测试立刻红。

⚠️ gazebo-chess 于 2026-07-08 迁去 soma-zero/sim，不在本仓这份清单里；它那份 awi_mcp.py
与这里几份的一致性**已无自动守卫**——改 AWI 协议时，记得手动去 soma-zero/sim/gazebo-chess/awi_mcp.py
同步一份（这条跨仓纪律就登记在此）。
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ⛔ 全集：加了新世界就往这里【追加】。sim-house-nav 于 v0.9 加入时漏登记，
#    v1.0 补上（当时五份其实没漂，纯属守卫没覆盖到——但那正是守卫会失效的方式）。
#
# 路径不再统一是 world/<名字>/：v1.1 起多了一份**在包里**的内置世界
# （src/worlds/desk，随 wheel 分发，好让 pip 装完有个去处）。它同样是一份逐字节副本、
# 同样要受这个守卫管——住在哪跟"会不会漂"没关系。
COPIES = {
    "world/sim-desk": ROOT / "world" / "sim-desk" / "awi_mcp.py",
    "world/sim-chess": ROOT / "world" / "sim-chess" / "awi_mcp.py",
    "world/camera": ROOT / "world" / "camera" / "awi_mcp.py",
    "world/sim-house-nav": ROOT / "world" / "sim-house-nav" / "awi_mcp.py",
    "src/worlds/desk（内置）": ROOT / "src" / "worlds" / "desk" / "awi_mcp.py",
}


def test_all_awi_mcp_copies_are_byte_identical():
    contents = {label: path.read_bytes() for label, path in COPIES.items()}
    ref_label = next(iter(COPIES))
    for label, data in contents.items():
        assert data == contents[ref_label], (
            f"awi_mcp.py 漂移：{label} 与 {ref_label} 不一致——改协议要各处同步"
        )
