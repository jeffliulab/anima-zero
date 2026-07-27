# boardgame-engine · ANIMA 的棋类顾问 service

一个独立的 **MCP server**（纯计算、无画面、无副作用）：大脑把它当「棋理顾问」问答用。
它不认识任何 world——挂载由 **Host（ANIMA）按 `config.services()` 组装**（标准 MCP 的 Host 组装模型），
所以同一个顾问能跟着大脑从仿真棋盘（sim-chess / gazebo-chess）走到真机械臂棋盘。

它是大脑的高层「想棋」帮手：**真机实时控制永不走 MCP**（那条留在身体内部的 ROS2/控制器/VLA）。

## 起服务

```bash
# 在 anima-zero 根
./.venv/bin/uvicorn services.boardgame_engine.app:app --host 127.0.0.1 --port 8108
```

可调项（本服务自带 env，不 import 脑 config）：`ANIMA_ENGINE_DEPTH`（搜索深度，默认 3）、
`ANIMA_ENGINE_TIME`（单步时限秒，默认 1.5）。

## 棋种分流

| 引擎内核 | 算法 | 状态 |
|---|---|---|
| `chess_engine.py` | Alpha-Beta 负极大 + 迭代加深 + 静止搜索（规则交 anima-chess） | ✅ **活**：暴露 `best_move` / `evaluate` / `legal_moves`（输入 FEN，非法 FEN 报可读错误） |
| `gomoku_engine.py` | Alpha-Beta + 棋型模式表（纯标准库） | ⏸ **就位待接** |
| `go_engine.py` | Naive MCTS，19×19 中国规则（纯标准库） | ⏸ **就位待接** |

**「就位待接」是什么、为什么**：两套内核已随 v0.6 搬入本包（获得版本管理），但**不暴露 MCP 工具**——
① anima-zero 侧目前没有任何消费方（sim-chess 世界的五子棋/围棋用世界自带实现当对手，与本服务无关）；
② 它们不用 FEN，「局面怎么作为工具入参传进来」的格式还没定。现在接 = 造无人用的死工具。
**接入条件**：出现真实消费方（比如大脑要在五子棋/围棋上也带顾问）时，先定局面输入格式，再在
`app.py` 里 `from . import gomoku_engine`（导入位已留）并补工具 + 测试。

## 关于 chess 引擎的「两份副本」（禁止去重合并）

`chess_engine.py`（本包，大脑的顾问）和 `world/sim-chess/chess_bot.py`（世界自带的电脑对手）
源自同一份算法，但**有意各存一份、零共享代码**：顾问与对手是两个角色，边界即隔离——
关掉本服务，世界的内置电脑照走；日后可各自独立调强弱（对手调弱做陪练、顾问保持最强）。
**请勿好心「去重」把它们合回一份。**
