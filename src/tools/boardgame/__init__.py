"""boardgame 域工具包：把"下一种棋"所需的整套原子能力（看/想/判/动）打包成一个适配器类。

- `base.py`：`BoardGameAdapter` 协议 + 注册表（通用对弈树只依赖这个协议）。
- `chess.py`：`ChessAdapter`（国际象棋的适配器）。将来五子棋 = 只写一个 `gomoku.py`。
"""
