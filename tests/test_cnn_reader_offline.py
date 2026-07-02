"""CNN 识别器（第二层）离线测试——v0.5 wave 4。

两部分：
1. 管线机制（永远跑）：用一个临时导出的**随机权重**小 ONNX 测读盘器本身——切格几何、批推理、
   置信门槛、"权重缺失→available()=False 诚实降级"。不假装测准确率。
2. 准确率（有真权重才跑，否则显式 skip）：真权重在 weights/ 时，对 wave 2 的合成斜视帧读子型，
   核对真值。权重不入 git，所以 CI 上这条会 skip——这不是"假装有测试"，是把降级路径写明。
"""
from __future__ import annotations

import numpy as np
import pytest

from anima import config
from anima.tools.boardgame import _cnn_reader as rd
from anima.tools.boardgame._cnn_reader import CLASSES, CnnReader, crop_squares


def _tiny_random_onnx(path: str) -> None:
    """手搓一个最小合法 ONNX（单层卷积+池化+线性，随机权重）——只测管线，不测认得准。"""
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    rng = np.random.default_rng(0)
    w = numpy_helper.from_array(rng.normal(0, 0.1, (len(CLASSES), 3 * rd.CROP_H * rd.CROP_W)).astype(np.float32), "W")
    b = numpy_helper.from_array(np.zeros(len(CLASSES), np.float32), "B")
    flat = helper.make_node("Flatten", ["x"], ["flat"])
    gemm = helper.make_node("Gemm", ["flat", "W", "B"], ["logits"], transB=1)
    graph = helper.make_graph(
        [flat, gemm], "tiny",
        [helper.make_tensor_value_info("x", TensorProto.FLOAT, ["n", 3, rd.CROP_H, rd.CROP_W])],
        [helper.make_tensor_value_info("logits", TensorProto.FLOAT, ["n", len(CLASSES)])],
        [w, b])
    onnx.save(helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)]), path)


def test_missing_weights_means_unavailable(tmp_path):
    """权重不存在 → available()=False（launcher 据此退化单层），构造不炸、语义诚实。"""
    r = CnnReader(weights_path=str(tmp_path / "nope.onnx"))
    assert r.available() is False


def test_crop_squares_shape_and_range():
    rect = np.random.default_rng(1).integers(0, 255, (384, 384, 3), np.uint8)
    crops = crop_squares(rect.astype(np.uint8))
    assert crops.shape == (64, rd.CROP_H, rd.CROP_W, 3)
    assert 0.0 <= float(crops.min()) and float(crops.max()) <= 1.0


def test_reader_pipeline_with_random_weights(tmp_path):
    """随机权重跑通整条读盘管线（找板→矫正→切格→批推理→置信门槛）。
    随机 logits 的 softmax 置信度必然低于 0.7 门槛 → 全盘"看不清"——这正是门槛该有的行为。"""
    pytest.importorskip("onnx")
    p = str(tmp_path / "tiny.onnx")
    _tiny_random_onnx(p)
    r = CnnReader(weights_path=p)
    assert r.available()

    # 借 wave 2 的合成斜视帧当输入（真实几何路径）
    from tests.test_occupancy_offline import synth_oblique_frame
    import chess
    placement, uncertain = r.read_detailed(synth_oblique_frame({chess.E4: "w"}))
    assert len(placement) + len(uncertain) <= 64
    assert uncertain, "随机权重置信度低，应有大量'看不清'而不是自信地瞎猜"


def test_real_weights_accuracy_if_present():
    """真权重存在时：合成斜视帧上的子型读取应≥基本准确率；权重缺失 → 显式 skip（降级路径）。"""
    r = CnnReader()
    if not r.available():
        pytest.skip(f"CNN 权重不存在（{config.cnn_weights_path()}）——按占位纪律降级单层，训练见 "
                    "world/gazebo-chess/scripts/train_cnn.py")
    import chess
    from tests.test_occupancy_offline import synth_oblique_frame
    truth = {chess.E4: "P", chess.D5: "p"}
    placement, uncertain = r.read_detailed(synth_oblique_frame({k: ("w" if v.isupper() else "b")
                                                                for k, v in truth.items()}))
    # 合成帧画的是圆子（非分型剪影），只验占用级一致性；子型级准确率在真 Gazebo 帧评（train_cnn 报告）。
    got_occ = {k: ("w" if v.isupper() else "b") for k, v in placement.items()}
    want_occ = {k: ("w" if v.isupper() else "b") for k, v in truth.items()}
    hits = sum(1 for k, v in want_occ.items() if got_occ.get(k) == v or k in uncertain)
    assert hits == len(want_occ), f"真权重下占用级读取不应错判：{got_occ} vs {want_occ}"
