<div align="center">

<a href="README.md"><img src="https://img.shields.io/badge/Language-English-2f81f7?style=flat-square" alt="English"></a>
<a href="README_zh.md"><img src="https://img.shields.io/badge/%E8%AF%AD%E8%A8%80-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-e67e22?style=flat-square" alt="简体中文"></a>

</div>

# sim-chess

ANIMA 的一个独立「世界」(AWI)：一套**仿真棋盘 + 内置棋手**，能独立跑「人 vs 电脑」，也能把任一方交给 ANIMA 控制。

**对大脑只给画面**：感知(MCP `resources/read anima://observation`)给一帧画面 + **空 state `{}`**（v0.4 简化后连 controllers/phase 都撤了，真值一概不给）；另有带外 `/stream`(MJPEG) 给人看。**绝不给棋盘结构化真值**(局面 / FEN)——大脑只能用眼睛看。命令结果用 MCP `tools/call` 的 `ok`(success/fail) 表达。

三个角色任意两个对弈：每一方控制者 ∈ `human / anima / bot`。

```
# 棋规则来自本仓的 anima-chess（MIT）；它还没上 PyPI，所以先从工作区装一次。
pip install -e ../../packages/anima-chess
cd world/sim-chess && pip install -e . && uvicorn server:app --port 8102
```
打开 `localhost:8102`：选双方控制者 → 开始；轮到"人"那方点起子格→点目标格走子。
