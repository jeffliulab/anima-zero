"""引擎 service 侧测试：FEN 校验的可读报错 + 三个工具的正常路径。

引擎内核已内聚进仓（services/boardgame_engine/chess_engine.py），无跨仓依赖、不再 skip。
"""
from __future__ import annotations

import pytest

from services.boardgame_engine import app as eng  # 引擎在模块导入时加载

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
