#!/usr/bin/env python3
"""激光测距 + 撞前刹车 验收（v1.0 wave2）。

四条硬验收：
  1. 射线**没打到机器人自己身上**——分组掩码起作用了（不然正前方永远读 0.13 米）；
  2. 八向读数**跟着朝向转**——原地转 90°，各方向的数应该整体轮转一格；
  3. 撞前刹车**真的在撞上之前停住**，且如实报出停下时前面还剩多远；
  4. 感知的 state 里**没有坐标、没有房间名**（红线，机器可查）。

用法： python test_lidar.py
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config as C                  # noqa: E402
from domus_scene import layout      # noqa: E402
from world import HouseNavWorld     # noqa: E402

L = layout()
GODVIEW_KEYS = ("x", "y", "pos", "pose", "room", "room_key", "room_label", "map")


def main() -> int:
    print("加载世界…")
    w = HouseNavWorld()
    time.sleep(2.0)                 # 等策略把姿态站稳，读数才不是半空中的
    sim = w.sim
    fails: list[str] = []

    # ---- 1) 没打到自己 ----
    c0 = sim.clearances()
    print("\n【1】八向读数（出生点）")
    print("   " + "  ".join(f"{k}={v:.2f}" for k, v in c0.items()))
    body_ish = {k: v for k, v in c0.items() if v < 0.30}
    if body_ish:
        fails.append(f"这些方向读数小于 0.30 m，八成打在机器人自己身上了：{body_ish}")
    print("   自打自己检查：" + ("❌ " + str(body_ish) if body_ish else "✅ 没有"))

    # ---- 2) 跟着朝向转 ----
    print("\n【2】原地左转 90°，看读数是不是整体轮转一格")
    r = sim.drive_turn(90.0, +1)
    c1 = sim.clearances()
    print(f"   实际转了 {abs(r['turned_deg']):.0f}°")
    print("   " + "  ".join(f"{k}={v:.2f}" for k, v in c1.items()))
    # 左转 90° 后，原来的"正左"应该变成"正前"（真实步态转不准，允许有出入 → 放宽比对）
    names = list(c0)
    rotated_ok = 0
    for i, nm in enumerate(names):
        before = c0[names[(i + 2) % len(names)]]     # 原来往左两格的那个方向
        after = c1[nm]
        if abs(before - after) < max(0.8, before * 0.4):
            rotated_ok += 1
    print(f"   八个方向里对得上的：{rotated_ok}/8")
    if rotated_ok < 5:
        fails.append(f"转身后读数没跟着轮转（只有 {rotated_ok}/8 对得上），朝向换算可能错了")

    # ---- 3) 撞前刹车 ----
    print(f"\n【3】一路往前走，看会不会在撞上之前停住（阈值 {C.BRAKE_STOP_M} m）")
    sim.reset()
    time.sleep(1.0)
    braked = False
    for i in range(4):
        res = w.invoke("move_forward", meters=C.MAX_MOVE_M)
        d = res["data"]
        print(f"   第{i + 1}次: 走了 {d['moved_m']:.2f}m  reason={d['reason']}  "
              f"前面剩 {d['front_m']}")
        print(f"        回话：{res['message']}")
        if d["reason"] == "braked":
            braked = True
            if d["front_m"] is None or d["front_m"] > C.BRAKE_STOP_M + 0.2:
                fails.append(f"刹车了却报出 {d['front_m']} m，和阈值对不上")
        if d["fallen"]:
            fails.append("往前走摔倒了")
            break
    if not braked:
        fails.append("一路走到底都没触发过刹车——要么阈值没生效，要么这条路上真没东西（换个方向再试）")

    # ---- 4) 红线：state 不许有上帝视角 ----
    print("\n【4】感知 state 的红线自查")
    st, _img = w.observe()
    leaked = [k for k in GODVIEW_KEYS if k in st]
    print(f"   state 的键：{sorted(st)}")
    print("   " + ("❌ 泄漏了 " + str(leaked) if leaked else "✅ 没有坐标/房间名"))
    if leaked:
        fails.append(f"感知里出现了上帝视角字段：{leaked}")

    sim.stop()
    print("\n" + "=" * 56)
    if fails:
        for f in fails:
            print("❌ " + f)
        print("=" * 56)
        return 1
    print("激光测距 ✅  跟随朝向 ✅  撞前刹车 ✅  观测红线 ✅")
    print("=" * 56)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
