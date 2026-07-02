"""离线训练 CNN 识别器（ChessCog 式逐格 13 类）并导出 ONNX——**训练工具，不进任何运行时**。

用法（用任何有 torch 的 python 跑，比如 conda 的 isaaclab 环境；不装进脑/世界 venv）：
    <有torch的python> scripts/train_cnn.py <数据集目录> [--epochs 20] [--out <onnx路径>]

数据集 = gen_dataset.py 的产物（frames/*.png + labels/*.json）。切格几何/类别顺序 **import 脑侧
`_cnn_reader.py` 的同一份契约**（CLASSES / crop_squares）——训练即推理，不给两套几何留漂移空间。
导出后把逐格准确率打给你看；不达标就别拷去 weights/（裁判会自动退化单层，诚实降级）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve()
_ANIMA_ROOT = _HERE.parents[3]                       # scripts → gazebo-chess → world → anima-zero
sys.path.insert(0, str(_ANIMA_ROOT))

from src.tools.boardgame import _cnn_reader as rd    # noqa: E402  共享契约（CLASSES/crop_squares）
from src.tools.boardgame import _occupancy_vision as ov  # noqa: E402  共享几何（找板/矫正）

VAL_FRAC = 0.15          # 验证集比例
BATCH = 256
LR = 1e-3
SEED = 7                 # 可复现划分


def load_dataset(root: Path) -> tuple[np.ndarray, np.ndarray]:
    import cv2
    xs, ys = [], []
    frames = sorted((root / "frames").glob("*.png"))
    skipped = 0
    for fp in frames:
        png = fp.read_bytes()
        frame = ov._decode_rgb(png)
        quad = ov._detect_board_quad(frame) if frame is not None else None
        if quad is None:
            skipped += 1
            continue
        rect = ov._rectify(frame, quad, cv2)
        crops = rd.crop_squares(rect)                # (64,H,W,3)
        label = json.loads((root / "labels" / (fp.stem + ".json")).read_text())["placement"]
        target = np.zeros(64, np.int64)              # 0 = 空
        for sq_name, sym in label.items():
            f = ord(sq_name[0]) - ord("a")
            r = int(sq_name[1]) - 1
            target[r * 8 + f] = rd.CLASSES.index(sym)
        xs.append(crops)
        ys.append(target)
    print(f"帧 {len(xs)}（找不到板跳过 {skipped}）→ 格样本 {len(xs) * 64}")
    return np.concatenate(xs), np.concatenate(ys)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset", type=Path, nargs="+")
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--out", type=Path,
                    default=_ANIMA_ROOT / "src" / "tools" / "boardgame" / "weights" / "cnn_squares.onnx")
    args = ap.parse_args()

    import torch
    import torch.nn as nn

    parts = [load_dataset(d) for d in args.dataset]
    x = np.concatenate([p[0] for p in parts])
    y = np.concatenate([p[1] for p in parts])
    x = torch.from_numpy(x.transpose(0, 3, 1, 2))    # NCHW
    y = torch.from_numpy(y)
    g = torch.Generator().manual_seed(SEED)
    idx = torch.randperm(len(x), generator=g)
    n_val = int(len(x) * VAL_FRAC)
    vi, ti = idx[:n_val], idx[n_val:]

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    net = nn.Sequential(                              # 小 CNN：够分 13 类剪影，别堆大模型
        nn.Conv2d(3, 16, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),   # 48x32 → 24x16
        nn.Conv2d(16, 32, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),  # → 12x8
        nn.Conv2d(32, 64, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),  # → 6x4
        nn.Flatten(), nn.Linear(64 * 6 * 4, 128), nn.ReLU(), nn.Dropout(0.2),
        nn.Linear(128, len(rd.CLASSES)),
    ).to(dev)
    opt = torch.optim.Adam(net.parameters(), lr=LR)
    # 类别加权：~85% 的格是空的，不加权模型会塌缩成"全猜空"（试点训练实测如此）。
    counts = np.bincount(y.numpy(), minlength=len(rd.CLASSES)).astype(np.float32)
    w = counts.sum() / np.maximum(counts, 1.0)
    lossf = nn.CrossEntropyLoss(weight=torch.tensor(w / w.mean()).to(dev))

    for ep in range(args.epochs):
        net.train()
        perm = ti[torch.randperm(len(ti), generator=g)]
        tot = 0.0
        for i in range(0, len(perm), BATCH):
            b = perm[i:i + BATCH]
            opt.zero_grad()
            loss = lossf(net(x[b].to(dev)), y[b].to(dev))
            loss.backward()
            opt.step()
            tot += float(loss) * len(b)
        net.eval()
        with torch.no_grad():
            pred = []
            for i in range(0, len(vi), BATCH):
                pred.append(net(x[vi[i:i + BATCH]].to(dev)).argmax(1).cpu())
            pred = torch.cat(pred)
        acc = float((pred == y[vi]).float().mean())
        print(f"epoch {ep + 1}/{args.epochs}  loss {tot / len(ti):.4f}  逐格准确率(验证) {acc:.4f}")

    # 分类别报告（哪类认不准一目了然）
    with torch.no_grad():
        for k, name in enumerate(rd.CLASSES):
            mask = y[vi] == k
            if int(mask.sum()) == 0:
                continue
            a = float((pred[mask] == k).float().mean())
            print(f"  类 {name or '空'}: n={int(mask.sum())} acc={a:.3f}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    net.cpu().eval()
    torch.onnx.export(net, torch.zeros(1, 3, rd.CROP_H, rd.CROP_W), str(args.out),
                      input_names=["x"], output_names=["logits"],
                      dynamic_axes={"x": {0: "n"}, "logits": {0: "n"}})
    print(f"已导出 ONNX → {args.out}（逐格准确率 {acc:.4f}；不满意就别用，裁判会退化单层）")


if __name__ == "__main__":
    main()
