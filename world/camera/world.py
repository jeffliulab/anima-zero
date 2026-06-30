"""camera 世界本体 —— 一个"摄像头世界"：把真实摄像头的画面交给 ANIMA 看，仅此而已。

这是 ANIMA 第一次看**真实物理世界**（不再是程序画出来的合成图）。本版定位：只看、能聊、不动手。

对大脑（ANIMA）：
- `capabilities()` 的 **tools 是空的** —— 这个世界不提供任何可执行动作。
  "ANIMA 在这里无法操作任何东西"是**结构上**保证的：没有工具可调，不是靠提示词哄它别动。
- `perceive()` 给【当前选中摄像头】的真帧 + 极简 state（选了哪个、有哪些可选、分辨率、是否在线）。
  没选 / 没开 → 不给图（image=None），state 里如实说明，绝不伪造画面。
- `invoke()` 谁来调都拒绝（本就没有动作）。

对人（世界自带控制面，不进 AWI、与大脑解耦）：选哪个摄像头、切换 —— 见 server.py 的 /cameras /select。
"""
from __future__ import annotations

import os

from capture import Camera

WORLD_VERSION = os.getenv("CAMERA_WORLD_VERSION", "0.3")   # 世界版本（env 可覆盖，不 inline 写死）


class CameraWorld:
    def __init__(self) -> None:
        self.cam = Camera()

    # ================= AWI 能力声明 =================
    def capabilities(self) -> dict:
        # 零 tools：这个世界只能看、不能操作。空列表即契约——大脑据此知道无动作可调。
        return {"name": "camera", "version": WORLD_VERSION, "tools": []}

    # ================= 看（perceive 的回程：画面 + 极简 state） =================
    def observe(self) -> tuple[dict, bytes | None]:
        """给【当前选中摄像头】一帧 + 极简 state。没选 / 抓不到 → image 为 None、online=False，并如实说明。"""
        png = self.cam.snapshot("png")
        st = self.cam.status()
        online = png is not None and st["online"]
        # 分辨率/帧率给【真正生效】的值（设备回读）；还没开就退回请求的分辨率、fps 给 None。
        resolution = ([st["actual_width"], st["actual_height"]]
                      if st["actual_width"] else [st["width"], st["height"]])
        state: dict = {
            "selected": st["selected"],
            "online": online,
            "available": [c["id"] for c in self.cam.cameras()],
            "resolution": resolution,
            "fps": st["fps"],
            "format": st["fourcc"],
        }
        if not online:
            # 如实告知"为什么没画面"——没选 / 打不开；绝不塞一张假图假装有画面。
            state["note"] = st["error"] or "还没选摄像头（请在世界页下拉框里选一个）"
        return state, png

    # ================= 动（本世界没有任何动作） =================
    def invoke(self, name: str, **args) -> dict:
        # 零 tools：任何 invoke 一律拒绝，并说清这个世界只能看、不能操作。
        return {"ok": False,
                "message": f"camera 世界只能看、不提供任何可执行动作（收到 invoke：{name}）"}
