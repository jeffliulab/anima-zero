#!/usr/bin/env python3
"""把训练出的 rsl-rl checkpoint 导出成本世界要用的 ONNX 策略（纯 CPU，不起 Isaac、不占 GPU）。

为什么自己写一个：上游 `play.py` 的导出在 rsl-rl 5.0 下已失效（属性名变更）。
与 locomotion 仓那个 G1 专用导出器的区别：**网络结构从 checkpoint 现场推断**，
不把观测/动作维度写死——换机器人（Go2 12 关节 vs G1 29 关节）、换网络宽度都不用改代码。

确定性推理 = actor 的 MLP 前向（训练时的高斯噪声 std 只用于探索，部署不要）。

用法：
    python export_policy.py <run_dir>              # 取该 run 最新的 model_*.pt
    python export_policy.py <run_dir> --out policy/policy.onnx
"""
from __future__ import annotations

import argparse
import glob
import os
import re

import torch
import torch.nn as nn

_HERE = os.path.dirname(os.path.abspath(__file__))


def latest_ckpt(run_dir: str) -> str:
    cks = glob.glob(os.path.join(run_dir, "model_*.pt"))
    if not cks:
        raise FileNotFoundError(f"{run_dir} 里没有 model_*.pt")
    return max(cks, key=lambda p: int(re.search(r"model_(\d+)\.pt", p).group(1)))


def build_actor_from_state(sd: dict) -> tuple[nn.Sequential, int, int]:
    """按 checkpoint 里 mlp.<i>.weight 的实际形状重建网络（层数/宽度全靠推断，不写死）。"""
    idx = sorted({int(m.group(1)) for k in sd if (m := re.match(r"mlp\.(\d+)\.weight", k))})
    if not idx:
        raise ValueError(f"checkpoint 里找不到 mlp.*.weight，认不出 actor 结构。键：{list(sd)[:8]}")
    layers: list[nn.Module] = []
    for n, i in enumerate(idx):
        w = sd[f"mlp.{i}.weight"]
        out_f, in_f = int(w.shape[0]), int(w.shape[1])
        layers.append(nn.Linear(in_f, out_f))
        if n < len(idx) - 1:
            layers.append(nn.ELU())      # rsl-rl 的 BasePPORunnerCfg 用 elu（见 rsl_rl_ppo_cfg.py）
    net = nn.Sequential(*layers)
    # 把权重按新模块的编号搬过去（原编号含激活层占位，重建后编号连续）
    remap = {}
    for n, i in enumerate(idx):
        remap[f"{2 * n}.weight"] = sd[f"mlp.{i}.weight"]
        remap[f"{2 * n}.bias"] = sd[f"mlp.{i}.bias"]
    net.load_state_dict(remap)
    net.eval()
    obs_dim = int(sd[f"mlp.{idx[0]}.weight"].shape[1])
    act_dim = int(sd[f"mlp.{idx[-1]}.weight"].shape[0])
    return net, obs_dim, act_dim


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", help="训练 run 目录（含 model_*.pt）")
    ap.add_argument("--out", default=os.path.join(_HERE, "policy", "policy.onnx"))
    args = ap.parse_args()

    ck_path = latest_ckpt(args.run_dir)
    ck = torch.load(ck_path, map_location="cpu", weights_only=False)
    if "actor_state_dict" not in ck:
        raise ValueError(f"{ck_path} 里没有 actor_state_dict，checkpoint 格式不对。顶层键：{list(ck)}")
    net, obs_dim, act_dim = build_actor_from_state(ck["actor_state_dict"])

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    dummy = torch.zeros(1, obs_dim)
    torch.onnx.export(net, dummy, args.out, input_names=["obs"], output_names=["action"],
                      dynamic_axes={"obs": {0: "batch"}, "action": {0: "batch"}}, opset_version=17)

    # 自检：ONNX 与 torch 的输出必须一致（导出坏了要当场发现，别等狗抽搐了才查）
    import numpy as np
    import onnxruntime as ort
    sess = ort.InferenceSession(args.out, providers=["CPUExecutionProvider"])
    probe = np.random.RandomState(0).randn(1, obs_dim).astype(np.float32)
    onnx_out = sess.run(None, {sess.get_inputs()[0].name: probe})[0]
    torch_out = net(torch.from_numpy(probe)).detach().numpy()
    max_err = float(np.abs(onnx_out - torch_out).max())
    if max_err > 1e-5:
        raise SystemExit(f"❌ ONNX 与 torch 输出不一致（max|err|={max_err:.2e}），导出有问题，拒绝交付。")

    print(f"导出成功 → {args.out}")
    print(f"  来源 checkpoint: {ck_path}（第 {ck.get('iter')} 轮）")
    print(f"  观测 {obs_dim} 维 → 动作 {act_dim} 维；一致性自检 max|err|={max_err:.2e} ✅")


if __name__ == "__main__":
    main()
