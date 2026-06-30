# sim-chess

ANIMA 的一个独立「世界」(AWI)：一套**仿真棋盘 + 内置棋手**，能独立跑「人 vs 电脑」，也能把任一方交给 ANIMA 控制。

**对大脑只给双流**：`/perceive`(画面 + 极简 state＝`{controllers, phase}`：谁执哪方、对局在哪个阶段) 和 `/stream`(MJPEG)。**绝不给棋盘结构化真值**(局面 / FEN)——大脑只能用眼睛看。命令结果用 `/invoke` 的 `ok`(success/fail) 表达。

三个角色任意两个对弈：每一方控制者 ∈ `human / anima / bot`。

```
cd world/sim-chess && pip install -e . && uvicorn server:app --port 8102
```
打开 `localhost:8102`：选双方控制者 → 开始；轮到"人"那方点起子格→点目标格走子。
