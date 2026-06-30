"""算「在某个世界点抓一个子」时，末端 link6 该摆成的位姿（位置 + 朝向四元数），纯几何、可离线测。

要点：
- 夹爪的指沿 link6 的 +Z 伸出，所以从上往下抓 = link6 的 +Z 朝下（世界 -Z）。基础朝向 = 绕 x 转 180°。
- 两指中间的抓取点(TCP) 在 link6 +Z 方向 TCP_OFFSET 处；link6 +Z 朝下时，TCP 在 link6 原点正下方 TCP_OFFSET。
  所以要把 TCP 放到抓取点 p，link6 原点要在 p 正上方 TCP_OFFSET：link6.z = p.z + TCP_OFFSET。
- 备用自由度（够不着/会撞时）：手腕自转（绕朝下的工具轴加 yaw）+ 接近方向倾斜（先竖直，0.4 基本只用竖直）。
- 返回若干候选位姿（最优在前：竖直、yaw=0），上层（arm_controller）逐个试 IK/规划，挑能成的。
"""
from __future__ import annotations

import math

import config
import geometry

Quat = tuple[float, float, float, float]   # (x, y, z, w)
Pose = tuple[tuple[float, float, float], Quat]


def quat_from_rpy(roll: float, pitch: float, yaw: float) -> Quat:
    """RPY(绕固定轴 x→y→z 复合，R=Rz·Ry·Rx) → 四元数 (x,y,z,w)。"""
    cr, sr = math.cos(roll / 2), math.sin(roll / 2)
    cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
    cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
    x = sr * cp * cy - cr * sp * sy
    y = cr * sp * cy + sr * cp * sy
    z = cr * cp * sy - sr * sp * cy
    w = cr * cp * cy + sr * sp * sy
    return (x, y, z, w)


def _down_quat(wrist_yaw_rad: float, tilt_rad: float = 0.0) -> Quat:
    """朝下的末端朝向：基础 roll=π 让 +Z 朝下；tilt 让它从竖直往外偏；wrist_yaw 绕竖直轴自转。
    简化实现：RPY(π, tilt, wrist_yaw)（0.4 主要 tilt=0）。倾斜方向的精细化留 0.5。"""
    return quat_from_rpy(math.pi, tilt_rad, wrist_yaw_rad)


def link6_pose_for_grasp(px: float, py: float, pz: float,
                         wrist_yaw_rad: float = 0.0, tilt_rad: float = 0.0) -> Pose:
    """给抓取点 (px,py,pz)，算 link6 该在的位姿（竖直抓时 link6 在抓取点上方 TCP_OFFSET）。"""
    return ((px, py, pz + config.TCP_OFFSET_M), _down_quat(wrist_yaw_rad, tilt_rad))


def candidates_for_point(px: float, py: float, pz: float) -> list[tuple[str, Pose, Pose]]:
    """某抓取点的 (标签, 接近位姿, 抓取位姿) 候选列表，最优在前。
    接近位姿 = 抓取位姿再抬高 APPROACH_SAFE_M。先竖直(tilt=0)各 wrist yaw，再逐档倾斜。"""
    out: list[tuple[str, Pose, Pose]] = []
    tilts = [0.0] + [math.radians(t) for t in config.APPROACH_TILT_DEG if t != 0]
    yaws = [math.radians(y) for y in config.WRIST_ROLL_DEG]
    for tilt in tilts:
        for yaw in yaws:
            (gx, gy, gz), q = link6_pose_for_grasp(px, py, pz, yaw, tilt)
            grasp = ((gx, gy, gz), q)
            approach = ((gx, gy, gz + config.APPROACH_SAFE_M), q)
            label = f"tilt{round(math.degrees(tilt))}_yaw{round(math.degrees(yaw))}"
            out.append((label, approach, grasp))
    return out


def candidates_for_square(square: str) -> list[tuple[str, Pose, Pose]]:
    """某棋格的抓取候选（格中心、棋子腰高为抓取点）。"""
    gx, gy, gz = geometry.grasp_xyz(square)
    return candidates_for_point(gx, gy, gz)


if __name__ == "__main__":
    # 离线自测：四元数单位化、朝下朝向、TCP 抬升、候选数量。
    import math as m

    def norm(q):
        return m.sqrt(sum(c * c for c in q))
    q = _down_quat(0.0)
    assert abs(norm(q) - 1.0) < 1e-9, q
    # 朝下：把 link6 +Z=(0,0,1) 用 q 旋转后应 ≈ (0,0,-1)
    x, y, z, w = q
    # 旋转 (0,0,1)：v' = q*v*q^-1，z 分量应 ≈ -1
    vz = (1 - 2 * (x * x + y * y))   # R[2][2]
    assert vz < -0.99, f"+Z 没朝下: R22={vz}"
    (gx, gy, gz), _ = link6_pose_for_grasp(0.30, -0.12, 0.028)
    assert abs(gz - (0.028 + config.TCP_OFFSET_M)) < 1e-9
    cands = candidates_for_square("e2")
    print("e2 抓取点(world) =", tuple(round(v, 3) for v in geometry.grasp_xyz("e2")))
    print("候选数 =", len(cands), "（第一个=最优：竖直 yaw0）")
    lbl, app, grp = cands[0]
    print("最优候选:", lbl, "approach link6 z=", round(app[0][2], 3), " grasp link6 z=", round(grp[0][2], 3))
    print("OK")
