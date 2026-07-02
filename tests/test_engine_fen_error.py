"""引擎 service 侧测试：FEN 校验的可读报错 + 三个工具的正常路径。

引擎源码在跨仓 3-anima-chess-engine（仓库结构派生路径）；外部环境没有该仓时整文件跳过（不造假）。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

_ENGINE = Path(__file__).resolve().parents[3] / "3-anima-chess-engine" / "chess" / "engine.py"
if not (os.getenv("ANIMA_CHESS_ENGINE_PATH") or _ENGINE.exists()):
    pytest.skip("引擎仓 3-anima-chess-engine 不在（跨仓依赖），跳过引擎 service 测试", allow_module_level=True)

from services import chess_engine_mcp as eng  # noqa: E402  （引擎在模块导入时加载）

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def test_best_move_returns_uci_on_valid_fen():
    uci = eng.best_move(START)
    assert isinstance(uci, str) and 4 <= len(uci) <= 5, "开局应返回一个 UCI 着法"


def test_garbage_fen_raises_readable_error():
    with pytest.raises(ValueError) as ei:
        eng.best_move("garbage")
    assert "FEN 不合法" in str(ei.value) and "核对" in str(ei.value), "报错要可读、要指路（让大脑能自我修正）"


def test_invalid_position_fen_raises_readable_error():
    # 语法对但局面不成立：黑方没有王
    with pytest.raises(ValueError) as ei:
        eng.best_move("8/8/8/8/8/8/8/K7 w - - 0 1")
    assert "局面不成立" in str(ei.value)


def test_evaluate_and_legal_moves_share_validation():
    assert isinstance(eng.evaluate(START), int)
    assert len(eng.legal_moves(START)) == 20, "开局恰有 20 个合法着法"
    with pytest.raises(ValueError):
        eng.legal_moves("nope")
