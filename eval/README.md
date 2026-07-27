# eval —— ANIMA 下棋记分台（独立）

一个**完全独立**的事后分析器：读 `logs/` 里下完的对弈、按主流象棋标准给 ANIMA 打分。
**不 import 主程序、不驱动大脑/世界、单独运行。** 形态 = 评测脚本（出 HTML+JSON），不是 plugin、不进运行时。

## 跑
```bash
# ⚠️ 这个分析器需要你**自己另外装**两样东西，它们**不是本项目的依赖**：
#     pip install chess          # python-chess（GPL-3.0）：读 PGN + 跟 UCI 引擎通信
#     apt install stockfish      # 或别的 UCI 引擎，用来做评分基准
# 为什么不像别处那样用本仓的 anima-chess：它有意不实现 PGN 解析和 UCI 通信，
# 而这两样正是事后分析要用的。运行时（大脑/世界/引擎 service）零 GPL，这个离线工具是你自己的选择。
./.venv/bin/python eval/eval_chess.py
# 或评一份标准 PGN：
./.venv/bin/python eval/eval_chess.py --pgn some_games.pgn
```
输出：`eval/out/scorecard.html` + `eval/out/scorecard.json` + 终端摘要。

## 评分标准
- **ACPL**（平均每步比引擎最佳少走的厘兵）—— 棋力金标准，越低越强；**accuracy%**（lichess 公式由 ACPL 推）；
  命中最佳着率；blunder/mistake/inaccuracy 计数（阈值 300/100/50cp）；**粗略估算 Elo**（量级参考）；ANIMA 视角胜/和/负。
- 引擎无关（不装引擎也有）：**分世界**的原语成功率与延迟（sim-chess 成功率=合法率；gazebo-chess 失败还含夹空/放偏等物理失败，语义不同、绝不合并）、对局数、物理失败合计。

## 数据从哪来
- `logs/games-*.jsonl` —— 世界每局结束落的**完整棋谱**（双方 UCI + 结果 + 谁执子）。下几盘棋就会有。
- `logs/awi-*.jsonl` —— 脑↔世界流量，取每次原语 `ms` 延迟与 `resp.ok` 成功率（统计哪些世界由 `EVAL_CHESS_WORLDS` 定，默认 sim-chess,gazebo-chess）。

## 装引擎（解锁 ACPL/Elo）
没装 UCI 引擎时，eval **如实只出引擎无关指标**（绝不假装能算棋力分）。装 Stockfish 后自动解锁：
```bash
sudo apt install stockfish        # 或 brew install stockfish / 官网下载
# 自定义引擎路径：
EVAL_ENGINE=/path/to/stockfish EVAL_DEPTH=16 ./.venv/bin/python eval/eval_chess.py
```

## 环境变量
`EVAL_ENGINE`(默认 stockfish) · `EVAL_DEPTH`(12) · `EVAL_LOGS_DIR`(../logs) · `EVAL_OUT_DIR`(./out)
