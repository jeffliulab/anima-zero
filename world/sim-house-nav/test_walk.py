#!/usr/bin/env python3
"""行走验收：狗在屋里到底能不能靠学习步态真的走起来、转起来。

这是 Phase A 的硬验收——**量净位移**，不看截图不看感觉（locomotion 项目"位移打假"的教训：
训练指标好看但固定命令下原地踏步 = 假成功）。

用法： python test_walk.py [--seconds 6] [--video out.mp4]
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config as C            # noqa: E402
from scene_assets import layout  # noqa: E402
from sim import HouseSim      # noqa: E402

L = layout()   # 场景布局（资产库）。⚠️ 2026-07-25 场景外置时这里漏改，
               #   一直写着 `import scene.layout`，本文件从那时起就跑不起来（v1.0 wave2 修）。


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=6.0, help="每个动作跑多久")
    ap.add_argument("--frames-dir", default="", help="存几张过程帧的目录（可选）")
    args = ap.parse_args()

    print("加载仿真…")
    sim = HouseSim()
    print(f"  策略: {os.path.basename(sim.policy_path)}")
    print(f"  关节映射: {len(sim.qadr)} 个（按名对齐，Isaac 序 ↔ MuJoCo 序）")
    print(f"  kp={sim.kp[0]:g} kd={sim.kd[0]:g} 力矩上限={sim.tau_max[0]:g}")
    print(f"  物理步长={C.PHYSICS_DT}s 控制周期={C.CONTROL_DT}s 分频={sim.decimation}")

    # 放到客厅中间的空地，给它跑直线的余量（避开家具）
    sim.reset()
    sim.data.qpos[0:3] = [-1.0, -1.6, float(sim.robot["start_height"])]
    sim.data.qpos[3:7] = [1.0, 0.0, 0.0, 0.0]      # 朝 +x
    sim.start()
    time.sleep(1.0)   # 让它先站稳

    x0, y0, yaw0 = sim.pose()
    print(f"\n站立 1 秒后：位置=({x0:.2f}, {y0:.2f}) 倾角={math.degrees(sim.tilt()):.1f}° "
          f"摔倒={sim.fallen()}")
    if sim.fallen():
        print("❌ 还没开始走就摔了——策略/部署对不上，先别往下走。")
        sim.stop()
        raise SystemExit(1)

    # ---- 直线行走 ----
    print(f"\n【测试 1】直线前进 vx={C.WALK_SPEED} m/s，{args.seconds}s")
    r = sim.drive(C.WALK_SPEED, 0.0, 0.0, args.seconds)
    ideal = C.WALK_SPEED * args.seconds
    print(f"  净位移 {r['moved_m']:.2f} m（理想 {ideal:.2f} m，达成 {100*r['moved_m']/ideal:.0f}%）")
    print(f"  末位姿 {r['pose']}  摔倒={r['fallen']}")
    walk_ok = (not r["fallen"]) and r["moved_m"] > ideal * 0.5

    # ---- 原地转向 ----
    sim.reset()
    sim.data.qpos[0:3] = [-1.0, -1.6, float(sim.robot["start_height"])]
    sim.data.qpos[3:7] = [1.0, 0.0, 0.0, 0.0]
    time.sleep(1.0)
    print(f"\n【测试 2】原地左转 wz={C.TURN_RATE} rad/s，4s（理想 ~{math.degrees(C.TURN_RATE*4):.0f}°）")
    r2 = sim.drive(0.0, 0.0, C.TURN_RATE, 4.0)
    print(f"  实际转了 {r2['turned_deg']:+.0f}°，位置漂移 {r2['moved_m']:.2f} m，摔倒={r2['fallen']}")
    turn_ok = (not r2["fallen"]) and abs(r2["turned_deg"]) > math.degrees(C.TURN_RATE * 4) * 0.4

    # ---- 存几帧看看 ----
    if args.frames_dir:
        os.makedirs(args.frames_dir, exist_ok=True)
        png = sim.frame_png()
        if png:
            with open(os.path.join(args.frames_dir, "after_turn.png"), "wb") as f:
                f.write(png)
            print(f"  存了一帧 → {args.frames_dir}/after_turn.png")

    sim.stop()
    print("\n" + "=" * 56)
    print(f"直线行走：{'✅ 通过' if walk_ok else '❌ 未通过'}")
    print(f"原地转向：{'✅ 通过' if turn_ok else '❌ 未通过'}")
    print("=" * 56)
    raise SystemExit(0 if (walk_ok and turn_ok) else 1)


if __name__ == "__main__":
    main()
