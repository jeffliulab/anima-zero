#!/usr/bin/env python3
"""从**活的** Isaac 训练环境导出 Go2 策略契约 → policy/contract.json。

为什么必须这么做（而不是照配置文件手抄）：策略的输入输出是一串没有名字的浮点数组，
它的**关节顺序**由 Isaac 的运动学树遍历决定、**缩放系数**散落在各观测项里。手写猜测一旦错位，
不会报错、只会让狗抽搐或原地不动，极难排查（G1 sim2sim 为此付出过惨痛代价）。
所以：顺序、默认站姿、增益、缩放、时序，全部从跑起来的 env 里问出来。

用法（isaaclab conda 环境；训练结束后跑一次即可）：
    python dump_contract.py --task Unitree-Go2-Velocity
"""
from __future__ import annotations

import argparse
import json
import os

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser()
parser.add_argument("--task", default="Unitree-Go2-Velocity")
parser.add_argument("--out", default="")
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()
args_cli.headless = True
app = AppLauncher(args_cli).app

import gymnasium as gym  # noqa: E402
import unitree_rl_lab.tasks  # noqa: E402,F401  （import 即注册所有任务）
from isaaclab_tasks.utils import parse_env_cfg  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))


def _tolist(t):
    return [float(v) for v in t.detach().cpu().numpy().ravel()]


def main() -> None:
    cfg = parse_env_cfg(args_cli.task, device="cpu", num_envs=1)
    cfg.observations.policy.enable_corruption = False   # 契约是确定性口径，不带训练噪声
    env = gym.make(args_cli.task, cfg=cfg).unwrapped
    robot = env.scene["robot"]

    joint_names = list(robot.data.joint_names)

    # 每个关节的 kp/kd/力矩上限：从执行器组里按名取，展开成"关节名 → 增益"
    gains: dict[str, dict] = {}
    for _group, act in robot.actuators.items():
        names = list(act.joint_names)
        for i, n in enumerate(names):
            def pick(attr, idx=i):
                v = getattr(act, attr, None)
                if v is None:
                    return None
                arr = v.detach().cpu().numpy().ravel() if hasattr(v, "detach") else [float(v)]
                return float(arr[idx]) if idx < len(arr) else float(arr[0])
            gains[n] = {
                "kp": pick("stiffness"),
                "kd": pick("damping"),
                # 力矩上限：没声明就给一个极大值（等于不钳制），绝不悄悄填 0（那会让狗瘫掉）
                "effort_limit": pick("effort_limit") or 1.0e9,
            }
    missing = [n for n in joint_names if n not in gains]
    if missing:
        raise SystemExit(f"这些关节没有对应执行器增益：{missing}——契约不完整，拒绝导出半成品。")

    # 观测项**顺序**与**缩放**都从 manager / cfg 现场读，不手抄
    term_order = list(env.observation_manager.active_terms["policy"])
    term_scales = {}
    for name in term_order:
        term_cfg = getattr(cfg.observations.policy, name, None)
        scale = getattr(term_cfg, "scale", None) if term_cfg is not None else None
        term_scales[name] = float(scale) if scale is not None else 1.0

    action_cfg = cfg.actions.JointPositionAction
    contract = {
        "task": args_cli.task,
        "joint_names": joint_names,
        "default_joint_pos": _tolist(robot.data.default_joint_pos[0]),
        "gains": gains,
        "term_order": term_order,
        "term_scales": term_scales,
        "history_length": int(getattr(cfg.observations.policy, "history_length", 1) or 1),
        "action": {"scale": float(action_cfg.scale),
                   "use_default_offset": bool(getattr(action_cfg, "use_default_offset", True)),
                   "dim": int(env.action_manager.total_action_dim)},
        "timing": {"policy_dt_s": float(env.step_dt), "physics_dt_s": float(cfg.sim.dt),
                   "decimation": int(cfg.decimation)},
        "obs_dim": int(env.observation_manager.group_obs_dim["policy"][0]),
    }

    out = args_cli.out or os.path.join(_HERE, "policy", "contract.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(contract, f, ensure_ascii=False, indent=2)
    print(f"契约已导出 → {out}")
    print(f"  关节 {len(joint_names)} 个，观测 {contract['obs_dim']} 维，"
          f"动作 {contract['action']['dim']} 维，策略周期 {contract['timing']['policy_dt_s']}s")
    print(f"  观测项顺序: {term_order}")
    print(f"  缩放: {term_scales}")
    env.close()


if __name__ == "__main__":
    main()
    app.close()
