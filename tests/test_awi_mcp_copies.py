"""四份 awi_mcp.py 副本的防漂移守卫。

世界是独立进程/各自 venv、不共享 import，所以每个世界目录各存一份 awi_mcp.py 拷贝；
协议改动必须四处同步（文件头就写着这条约定）。以前只靠自觉，这里字节级核对——
谁改了一份忘了同步另外三份，这个测试立刻红。
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORLDS = ["sim-desk", "sim-chess", "camera", "gazebo-chess"]


def test_awi_mcp_four_copies_byte_identical():
    contents = {w: (ROOT / "world" / w / "awi_mcp.py").read_bytes() for w in WORLDS}
    ref = WORLDS[0]
    for w, data in contents.items():
        assert data == contents[ref], (
            f"awi_mcp.py 漂移：world/{w} 与 world/{ref} 不一致——改协议要四处同步"
        )
