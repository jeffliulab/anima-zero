# 更新日志

ANIMA Zero 的版本记录。格式大致参照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/);
破坏性变更用 `!` 标注。

## [0.1.0] — 2026-06-27 — ANIMA Zero V0.1 正式封版

最轻量的具身 agent 框架封版:**脑(System 2)只想不动,世界(独立进程)负责看与做,中间一套
AWI(Anima World Interface)接口**。自带可跑的 `sim-desk` 世界(桌面 + 笔 + 画布)、三栏网页、5 个可换大脑。
按 deep-research 背书的设计哲学(教程 5.1)搭成。本条目取代下面两条未发布 / 内部里程碑。

### 架构 / 新增
- **AWI(`src/awi.py` + `src/world_client.py`)**:脑↔世界接口标准(借鉴 MCP / ROS),四端点
  `/capabilities` `/perceive` `/invoke` `/reset`;`RemoteWorld` 是瘦客户端,**换世界 = 换 URL**(sim2sim / 真机同理)。
- **世界独立成进程**:示例世界 `sim-desk`(桌面 + 笔 + 可涂画画布,工具 `move_pen` / `draw` / `erase`),
  自带实时视频流 `/stream`(MJPEG)、`/health` 探活、`/awi-events` 流量、以及人类界面(笔/橡皮/移动,拖出选区作画)。
- **会话(`src/session.py`)**:一次任务一个会话,**按世界单活 + 冻结**(同世界开新会话冻结旧的,保护物理设备);
  记忆存本地 JSON;可中途换脑。世界清单走 `ANIMA_WORLDS` 配置。
- **通用主循环(`src/orchestrator.py`)**:看 → 想 →(过安全闸)→ 动 → 再看,转到大脑只出文字;每轮产结构化轨迹。
- **原生工具调用(tool-calling)**:工具作为 API 的 `tools` 参数传给大脑、读回结构化 `tool_calls`,**不在提示词里写 JSON**;
  云端(OpenAI / Claude)+ 本地 Ollama 走同一条 `OpenAICompatLLM` 路。
- **上下文(`src/context.py`)**:滑动窗口 + 只发最新一张图。
- **安全闸(`src/safety.py`)**:动作前一道不经过 LLM 的确定性闸,`default_allow` 显式可控(仿真放行,上真机关掉再填硬检查);
  只拦「会改世界」的动作(按 kind 单一来源 `NON_MUTATING_KINDS` 判定)。
- **AWI 可视化**:世界端网页(状态条 + 流量 terminal)+ ANIMA 端 `/awi` 仪表盘;流量落盘 `logs/awi-*.jsonl`。
- **能力握手缓存**:能力连接时握手一次后缓存,主循环与仪表盘不再每轮 / 每几秒重问世界;在线探活改走不记流量的 `/health`。
- **前端(Next.js 15 / React 19 / Tailwind v4)**:三栏 + 两层折叠 + 历史只读 + 切换大脑分隔线 + 流式输出(SSE)+ markdown。
- **可换大脑(`src/llm/factory.py`)**:5 个看图大脑——在线 Opus 4.8 / Haiku 4.5 / GPT-5.5 / GPT-4.1-nano,
  本地 Qwen3-VL 8B(经 Ollama,免费);一张登记表,默认脑可配。

### 设计要点(经 deep-research 背书,详见 README)
- **把工具当「按需调用的能力」而非「必须执行的清单」**:靠 system prompt + 工具 description 写清「何时调 / 何时不调」+
  把画面 framing 成环境背景。实测让弱模型(gpt-4.1-nano)在「你好」时从 8/8 乱调动作 → 0/16 不调。
- 期望 × 观测 × 裁判;硬安全不写在提示词里;单脑编排、不盲目并行。

### 变更 / 移除(相对更早的 ANIMA O1 原型)
- `!` 删除整个 L0–L5 栈 / 五因子评估 / BCI 信号层,由 AWI 标准 + 通用 agent loop 取代。
- `!` 命名统一 `object → world`、接口正名 **AWI**;`/api/chat` 按 `session_id`;依赖换成
  `anthropic` / `openai` / `fastapi` / `uvicorn` / `pillow` / `httpx` / `python-dotenv`。

### 修复
- OpenAI 路径去掉写死的 `max_tokens`(新模型如 GPT-5.5 只认 `max_completion_tokens`,传 `max_tokens` 会 400)。
- 前端「你好却显示 move_pen」的串台(ChatPanel 改不可变更新);LLM 图片文案 `object → 世界`。

### 说明
- Pre-alpha,1.0 之前接口可能变。真机安全硬检查、视觉裁判、技能库按依赖顺序后做。

## [0.1.0-pre] — 2026-06-25 — 重构起点(虚拟桌面骨架,内部里程碑)

从零重写。**本版取代更早的 `0.1.0`(即「ANIMA O1」的 L0–L5 / 五因子原型,2026-04-21,旧代码已删除)**
——不复用其中任何东西。这一版立起新的抽象,以及一个最小、自包含、可复现的 demo。

### 新增
- **object 标准**(`anima.object`)—— 一份小契约(借鉴 MCP / ROS),任何外部实体实现它即可即插即用:
  `capabilities()`(能力协商,带 JSON Schema 的工具)、`perceive()`(双路:`image_png` + 结构化 `state`)、`invoke()`。
- **object 注册表**(`anima.registry`)—— 注册多个 object,同一时刻只绑定一个。
- **通用 agent loop**(`anima.orchestrator`)—— ReAct / TAO 循环,**感知入口 = 当前连接的 object**:
  没连 → 纯聊天;桌面 → 渲染图;将来摄像头 / MuJoCo → 摄像头帧。内置 `list_objects` /
  `connect_object` / `disconnect_object`;每个动作后闭环重感知。
- **解耦的 LLM 层**(`anima.llm`)—— 一家一个文件:`ClaudeLLM`、`OpenAICompatLLM`(OpenAI + 本地 Ollama),
  统一接口;`make_llm()` 按 `ANIMA_BRAIN` 选脑。五个能看图的大脑 —— 在线:Opus 4.8、Haiku 4.5、
  GPT-5.5、GPT-4.1-nano;本地:Qwen3-VL 8B(经 Ollama,免费的开发测试脑)。无 mock。各大脑分开支持、
  各自可配,配置见 `.env.example`;怎么再加见 `src/llm/README.md`。
- **第一个 object** `object/desk-sim` —— 虚拟桌面 + 一支笔;用 Pillow 自渲染,暴露 `move_pen`(tool)
  和 `move_object`(skill)。
- **展示层** `presentation/` —— FastAPI 后端(感知图 + 聊天)+ Next.js 15 / React 19 / Tailwind v4 前端
  (左传感区、右聊天)。

### 变更
- `!` 包布局:扁平 `src/` 映射成 `anima` 包(不再有 `src/anima`);构建后端换成 setuptools。
- `!` 依赖:去掉 `numpy` / `py_trees`;加入 `anthropic`、`openai`、`fastapi`、`uvicorn`、`pillow`、
  `python-dotenv`。

### 移除
- `!` 整个 L0–L5 栈、五因子评估、Test-and-Check 闸、通用 `TaskSpec`、BCI 信号层及其测试 —— 由上面的
  object 标准 + agent loop 取代。

### 说明
- pre-alpha,`1.0.0` 之前接口可能随时变。README 还需补一节讲新抽象(object 标准 / 注册表 /
  agent loop / 感知入口取决于 object)。

## 模板

```
## [x.y.z] — YYYY-MM-DD

### 新增 / 变更 / 弃用 / 移除 / 修复 / 安全
- ...
```
