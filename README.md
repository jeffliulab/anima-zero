<div align="center">

<h1>ANIMA Zero</h1>

<p>
  <img src="https://img.shields.io/badge/python-3.11+-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-backend-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/Next.js-15-black?logo=nextdotjs" alt="Next.js">
  <img src="https://img.shields.io/badge/Status-Pre--alpha-orange" alt="Status">
  <img src="https://img.shields.io/badge/License-Apache_2.0-green" alt="License">
</p>

<p>
  <strong>ANIMA 是一台具身机器人的「脑」:它只想、不动手。它决定「做什么」,身体决定「怎么动」。</strong>
</p>

<p>
  <a href="https://github.com/jeffliulab/soma-zero"><img src="https://img.shields.io/badge/身体-SOMA_Zero-purple" alt="SOMA Zero"></a>
</p>

</div>

> 这份 README 讲的是**顶层思维**:ANIMA 是什么、怎么运转、为什么这么设计。代码细节以仓库为准。
> 当前 v0.x 先出中文版,双语(英文)版留到 v1.0。

---

## ANIMA 是什么

ANIMA 本质是一个 **agent(智能体)**——和 Claude Code、Codex 这类当今最强的编码 agent 是同一类东西,
只不过把「眼」换成相机、「手」换成机械臂(背后是一个学习式的视觉-语言-动作策略,VLA)。它把一个目标变成
一串**安全、经过核验**的动作,交给「世界」去执行,再根据反馈判断成没成、要不要重试。

这就是认知科学的 **System 1 / System 2** 分工:**ANIMA 是 System 2**——慢、深思,每个决策跑一次;
身体是 **System 1**——快、反射、高频闭环。这套切分是当下主流机器人大脑的共识(π0.5、GR00T N1、Figure Helix)。
配套的身体在另一个仓库:[`soma-zero`](https://github.com/jeffliulab/soma-zero)。

### 这个项目在证明什么(定位)

不是"又一个能接任意世界的通用框架"那么空——而是想把**长程、需要闭环纠错的具身任务**做到底,而且**可复现**。
**象棋**是验证载体:它长程(一盘几十步)、要视觉读盘、要推理走子、还要在走错/抓偏时纠错——一个任务把"会想 + 看得见 + 出错能纠"全考到。

- **可复现 ≠ 看着 demo 跑通**:独立的 [`eval/`](eval/) 读对弈日志、用 Stockfish 按 **ACPL** 等主流标准给出一张 `python eval/eval_chess.py` 就能复现的记分卡。
- **安全是设计的一部分**:所有真机命令**由人亲手执行**——这不是限制,是有意的 *safe-stop* 设计(舵机臂断电即失力,真正的急停 = 人不按那个按钮),且每个动作都可审计。
- **"能驱动很多异构世界"是架构内核,不是卖点**:AWI 刻意精简、与 MCP 语义兼容(换世界只换地址,大脑一行不改);但它是手段,真正想做透的是上面那件事。
- **失败恢复**目前主要待**真机**阶段兑现(仿真棋盘很难"下错子"),是路线图上的下一块——不在此假装已完成。

---

## 一、人 - ANIMA - 世界:三者关系

最关键的一点:**「世界」是一个独立运行的程序**(仿真器 / 真机),ANIMA 不碰它的内部,只隔着一套
「看 / 动」的接口去观测、操作它——就像看真实世界一样。人开会话、看结果;ANIMA 在中间想和编排;世界在另一头自己跑。

```
   [ 人 ]                    [ ANIMA = 脑 / 框架 ]                  [ 世界 = 独立进程 ]
  开会话 ── 选世界/选脑 ─▶  会话(本地记忆) + 主循环          ──HTTP──▶  sim-desk / 棋 / 人形
  看折叠轨迹 ◀── 输入图+真值 / 思考 / 回复                   ◀──HTTP──   看(perceive)· 动(invoke)
                                                  世界自己另有一套给人用的界面(可手动拨弄世界)
```

人甚至可以**绕过大脑、直接在世界自己的界面里拨弄它**(比如拖动桌面上的笔),ANIMA 下一次 perceive 就会
看到世界变了——这就证明了「世界是独立的,ANIMA 只是个观测者 + 指挥者」。

---

## 二、框架结构

ANIMA 不认识任何具体世界,只认一套 **AWI** 加几个外围件:

| 部件 | 一句话 |
|---|---|
| **AWI(Anima World Interface)**(`src/awi.py` + `world_client.py`) | 脑↔世界的接口标准:定个标准,谁符合谁就能接入(像 MCP / ROS);anima 用瘦客户端按 URL 连远程世界 |
| **注册表**(`src/registry.py`) | 登记有哪些世界(名字 + URL);世界清单配在 `.env` 的 `ANIMA_WORLDS`,加世界 = 加一行配置 |
| **会话**(`src/session.py`) | 一次任务一个会话,**按世界单活 + 冻结**(同一个世界同时只允许一个活跃会话,安全);记忆存本地 |
| **上下文**(`src/context.py`) | 发给大脑的历史 = 滑动窗口 + 只发最新一张图(老图只存不发,防上下文腐烂) |
| **安全闸**(`src/safety.py`) | 动作下发前一道**不经过 LLM 的确定性检查**;只拦「会改世界」的动作(仿真默认放行,上真机把 `default_allow` 显式关掉、再填硬检查) |
| **裁判** | 是世界提供的一个**确定性工具**,LLM 学会去调它确认成没成——不靠 LLM 自己看图说「做好了」 |
| **编排器**(`src/orchestrator.py`) | 把上面这些串成一个简单的主循环 |

---

## 三、请求处理链路:一条消息从进到出

顶级 agent 的一条共识:**主循环简单到就是个 while 循环,复杂度全在外围**(记忆、验证、安全)。
ANIMA 照这个来——一条用户消息进来,主循环最多转 N 轮(`DEFAULT_MAX_STEPS`),每一轮就是
「**看 → 想 →(过安全闸)→ 动 → 再看**」,直到大脑只出文字 = 收尾。不上行为树这类重型框架。

```
   用户发一句话
        │
        ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │ ① 看 perceive   向世界要一帧画面 + 结构化真值        (AWI: GET /perceive) │
   │      │                                                                  │
   │      ▼                                                                  │
   │ ② 想 LLM        把 [系统说明 + 历史 + 工具清单 + 这帧画面] 交给大脑,        │
   │      │           大脑决定:只回话?还是调某个工具?(见 §五 工具调用)        │
   │      ├──── 只回话 ───────────────────────────────▶ 作为最终回复,收尾 ✅   │
   │      │                                                                  │
   │      ▼ 要调工具                                                          │
   │ ③ 过安全闸       「会改世界」的动作先过一道不经过 LLM 的确定性检查           │
   │      │           (打招呼/只读/裁判类不算改世界,直接放行)                  │
   │      ▼                                                                  │
   │ ④ 动 invoke     把工具调用交给世界执行               (AWI: POST /invoke)   │
   │      │                                                                  │
   │      └──────── 回到 ① 重新看一眼(闭环纠错)───────────────────────────────┘
```

对应代码 `src/orchestrator.py` 的 `handle()`(整段返回)/ `handle_stream()`(边跑边流式推给前端)。
**工具调用发生在第 ② 步(大脑决定调谁)和第 ④ 步(世界执行)——它怎么实现的,见下面 §五。**

每一轮还会产出一份**结构化轨迹**:这一步看到的图 + ground truth(输入)、想了什么、调了哪些工具(思考)、
最终回复。前端把它做成**两层折叠**,方便排查「它到底看到了什么、怎么想的」。

---

## 四、怎么接入一个世界(AWI)

任何「世界」实现下面这套 **AWI(Anima World Interface)** HTTP 接口,ANIMA 那边换个 URL 就能接:

```
GET  /capabilities  ->  这个世界有哪些高层动作(语言可读,不是关节角)
GET  /perceive      ->  当前画面(图)+ ground truth(结构化状态)
POST /invoke        ->  执行一个动作,返回结果
POST /reset         ->  世界自己的复位(给世界的人类界面用)
```

世界还另外推一条**实时视频流**(`GET /stream`,MJPEG)给网页看(摄像头 / MuJoCo 以后同理),并提供一个轻量
探活端点(`GET /health`,ANIMA 据此判断世界在线 / 离线,故意不计入流量)。ANIMA 有个 **AWI 仪表盘 `/awi`**,
把所有连接、各世界的能力清单、实时 AWI 流量都展示出来;能力在连接时**握手一次后缓存**(不再每轮 / 每几秒重问),
流量同时**落盘到 `logs/awi-*.jsonl`** 方便追溯。

这一版自带一个例子:**[`sim-desk`](world/sim-desk)**——一张虚拟桌面 + 一支笔 + 一块可涂画的画布,声明三个工具
`move_pen` / `draw` / `erase`,还能让人在它自己的界面里手动作画 / 擦除,模拟「真实世界被人改变」。以后:

- **下棋**:把世界换成「棋盘 + 棋臂」,高层动作变成「把 e2 走到 e4」,裁判用 `python-chess`(期望)对比视觉(观测)。
- **人形行走**:把世界换成 MuJoCo 人形,高层动作变成「走到门口 / 左转 90°」,裁判对比目标位姿和实测位姿。

**所谓 sim2sim、上真机,就是让大脑去连不同的世界**——接口一样,大脑一行都不用改。

---

## 五、工具调用(Tool Use)是怎么实现的

ANIMA **不在提示词里让模型「输出 JSON」**,用的是各家大模型 API 的**原生工具调用(function calling / tool use)**。

- ❌ 老办法:在 prompt 里写「请按 `{"action":...,"args":...}` 输出」,模型吐一段文本,你自己正则 / `json.loads` 去抠——脆、易跑偏。
- ✅ 原生工具调用(我们用的):把工具清单作为**独立参数**交给 API,模型经专门训练,会把调用放进一个**专门的结构化字段**返回;格式由 API 保证,我们直接读字段。

**三步(对应代码 `src/llm/`):**

1. **把工具交给 API**(不写进 system prompt)。每个工具 = 名字 + 描述 + 参数 JSON Schema,**来自世界声明的 `/capabilities`**,框架原样转发。
   `openai_compat.py` 的 `_tools()` 转成 `{"type":"function","function":{name,description,parameters}}`;`claude.py` 的 `_tools()` 转成 `{name, description, input_schema}`。
2. **让模型自己决定调不调**:`tool_choice="auto"` —— 可以调一个 / 多个,**也可以一个都不调、只回话**。正因为是 auto,「你好」才能只回文字;若改成 required / any 会强制它每轮必须调一个工具。
3. **从结构化字段读回调用**(不解析正文):
   - OpenAI / Ollama:读 `message.tool_calls`,参数在 `function.arguments`(一个 JSON 字符串)→ `json.loads`。
   - Claude:读 `content` 里 `type=="tool_use"` 的块,拿 `name` + `input`(已是对象)。

**关键心智模型——谁负责什么:**

| 负责 | 由谁管 |
|---|---|
| **要不要调、何时调**(行为) | system prompt + 工具 description ←「打招呼也乱调工具」就是改这里修好的 |
| **怎么把这次调用表达成 JSON**(机制) | `tools` 参数 + 结构化返回字段(API 这层管,JSON 不进提示词) |

**怎么自己看实物**:发一条消息后,后端会话记录里 `role:"tool"` 那条、以及 `/awi` 仪表盘的 invoke 流量,就是真实的工具调用;轨迹里某轮 `tool_calls` 字段空不空,就代表「这轮调没调工具」。

---

## 六、换大脑 & 本地模型

**换脑零成本**:5 个大脑登记在 `src/llm/factory.py` 一张表里(名字 / 显示名 / 版本号 / 怎么创建 / 是否配置好)。
OpenAI 和本地 Ollama **共用** `OpenAICompatLLM`(只换 `base_url`),Claude 用 `ClaudeLLM`。在网页里下拉换,别处一行不动。

**本地 Ollama 也是原生工具调用**:Ollama 暴露 OpenAI 兼容口,内部把 `tools` 按模型自己的对话模板注入 prompt、再把模型输出**解析回结构化 `tool_calls`**——所以我们代码零改动,拿到的同样是 `tool_calls`,不用手写 JSON。

> ⚠️ **本地模型可靠性参差**:有的产非法 JSON、有的工具一多就乱;Ollama 官方都提醒某些路径「只建议用于一次只返回一个工具调用的模型」。目前 **Qwen3 系最稳**(漏调率最低),这也是默认本地脑选 `qwen3-vl` 的原因。**建议先用云端(GPT / Claude)把闭环验证通,本地当备选。**

**给「原生支持差的本地模型」的可靠性兜底(以后可选,当前未做):**
- **受约束解码 / GBNF 语法(llama.cpp)**:在 token 层强制输出符合 JSON Schema——非法 token 概率归零,**生成的 JSON 形状一定合法**。Ollama v0.5+ 可直接给 `format` 参数传 JSON Schema,内部转 GBNF。⚠️ 它只保证「格式对」,不解决「该不该调、何时调」(那仍归 prompt)。
- **Instructor / Outlines**:Python 库,用 Pydantic 校验 + 自动重试(把校验错误回灌模型重出)逼出合法结构。

---

## 七、设计哲学(详见教程 5.1)

- **慢脑快手**:ANIMA(System 2)只想、不动;那只「快手」(System 1,VLA / 行走策略)藏在世界的 invoke 背后。
- **期望 × 观测 × 裁判**:逻辑真值(应该怎样)在工具里(如 python-chess),物理真相(实际怎样)在眼睛里,
  判定权在脑——脑拿这两个比对,而不是让 LLM 自己看图打分。
- **硬安全不写在提示词里**:提示词对模型只是「参考」,它可以不听;要真拦住一个动作,必须有一道不经过 LLM 的
  确定性闸。连续控制(人形)还需要世界侧就近控制器的快确定性盾(MPC / CBF)。
- **单脑编排、不盲目并行**:一个编排者收口,串行主干;不为了「多 agent」而堆一堆 LLM。

这些都来自我们对 2025–2026 业界 agent + 机器人框架的调研,详细展开见配套教程「5.1 agent 系统」。

---

## 八、快速上手

需要三件一起跑:**世界(sim-desk)· ANIMA 后端 · 网页**。

```bash
# 1) 起世界(独立进程)
cd world/sim-desk && pip install -e . && uvicorn server:app --port 8100

# 2) 起 ANIMA 后端
pip install -e .                       # 在 anima-zero 根目录
cp .env.example .env                   # 填一个 API key(或配本地 Ollama)
uvicorn presentation.server:app --port 8000

# 3) 起网页
cd presentation/web && npm install && npm run dev      # 默认 :3000
```

然后打开 `localhost:3000`:**新建会话 → 选世界 + 选大脑 → 对话**(例:「把笔移到右上角」)。
大脑在网页里下拉选(Opus 4.8 / Haiku 4.5 / GPT-5.5 / GPT-4.1-nano / 本地 Qwen3-VL),配置在 `.env`。
也可以打开 `localhost:8100` 手动拖笔,看 ANIMA 那边能不能观测到变化。

---

## 九、Chess Mode：下棋(行为树 + 视觉 + 通用对弈 skill)

ANIMA 的第一个 **skill**:陪你下国际象棋。它示范了几层新概念(全程仿真,为将来接真摄像头+机械臂铺路)。

- **world `sim-chess`**(`world/sim-chess/`):一套独立可运行的棋具——握唯一真值、渲染棋盘、内置电脑棋手、每方控制者可选 人/ANIMA/电脑(三阶段:未开始/对弈中/已结束)。**对大脑只给「画面 + 极简 state(`{controllers, phase}`:谁执哪方、对局阶段)」,绝不给棋盘结构化真值**(局面/FEN);ANIMA 靠**看图**读盘,经 `take_seat` 自己选边就座,只能**单向**发走子命令 `move(from,to,piece)`,世界回 success/fail。
- **ANIMA 的眼睛 `read_board`**(`src/tools/boardgame/_vision.py`):对画面做**图像识别**认出局面(吃像素、不读内部数据);接口=图→局面,以后换真视觉模型即可。
- **对弈行为树 = Chess Mode**(`src/behavior/trees/boardgame.py`,py_trees):**skill 之上的循环层**,每秒 tick 自主维持对弈、判进入/退出/中断、轮次判断。走子管线全确定性(看盘→引擎出手→发命令→看成败);**LLM 只在「解说」和高层判断介入**。
- **skill = 说明书**(`src/skill.py` + `src/skills/boardgame.py`):游戏无关的"对弈陪伴"指令(不含循环、不挑棋);进对局**一句话到位**——大脑从对话理解你执哪方,launcher 自动就座+开局+起树。**可插拔棋种适配器**(`src/tools/boardgame/{base,chess}.py`)让同一棵树支持象棋/五子棋/围棋;**引擎解耦**——只有 `chess.py` 适配器碰你自己的引擎,升级棋力只换它。

> 概念边界:**world**=物理接口(只看与动)、**行为树**=循环层(怎么转/何时停)、**skill**=说明书(怎么用工具)、**tool**=原子能力(一进一出)、**棋种适配器**=每棋的眼睛+引擎。skill ≠ tool。

**跑法**:先把 sim-chess 世界起起来,后端**同时**注册两个世界(sim-desk + sim-chess),会话连 sim-chess,然后在聊天里说「我们下棋吧」即可:
```bash
# 终端1:起棋具世界(独立进程)
cd world/sim-chess && pip install -e . && uvicorn server:app --port 8102
# 终端2:后端同时注册两个世界 —— ⚠️ 加新世界要追加,别把 sim-desk 写没了
ANIMA_WORLDS="sim-desk=http://localhost:8100,sim-chess=http://localhost:8102" uvicorn presentation.server:app --port 8000
# (其实不设 ANIMA_WORLDS 也行:默认清单已含 sim-desk + sim-chess)
# 网页新建会话(世界选 sim-chess)→ 说"我们下棋吧,我执黑"→ 自动选边+开局,浮现 Chess Mode 面板
```

---

## 状态

**v0.2(Pre-alpha),持续迭代中。** v0.1 封版了顶层架构(世界独立 + 会话 + 主循环 + 外围 hook + 原生 tool-calling);
v0.2 在这套框架上长出第一个**技能 = Chess Mode**(技能 + 对弈行为树 + 只给画面的 sim-chess 世界 + 通用运行时 HITL/分级安全闸 + 独立 eval 记分台)。
真机安全硬检查、视觉裁判升级、失败恢复按依赖顺序后做(失败恢复待真机阶段兑现)。`anima-zero` 是完全开源的 Zero 线展示版。

## License

[Apache License 2.0](LICENSE) — Copyright 2026 Jeff Liu Lab
([jeffliulab.com](https://jeffliulab.com),GitHub [@jeffliulab](https://github.com/jeffliulab))。
