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
身体侧不在本仓——任何实现 AWI(MCP) 的身体都能作为「世界」接入(见「四、怎么接入一个世界」),大脑一行不改。

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
  开会话 ── 选世界/选脑 ─▶  会话(本地记忆) + 主循环          ──MCP───▶  sim-desk / 棋 / 人形
  看折叠轨迹 ◀── 输入图+真值 / 思考 / 回复                   ◀──MCP───   看(resource)· 动(tool)
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
| **挂载服务**(`src/service_client.py`) | **world 之外的第二类端点:顾问**——纯计算、无画面、无副作用(如象棋引擎),问答拿反馈;由 world 自己声明(`anima://services`),脑握手后自动连接、工具并进同一张工具单 |
| **统一日志**(`src/session_log.py`) | **Session Logs**:每会话一条流水(`logs/sessions/<sid>.jsonl`),LLM 调用/世界往返/服务调用按时间合并——「看到什么→想了什么→调了什么」一条链可查、可一键复制 |
| **裁判** | 是世界提供的一个**确定性工具**,LLM 学会去调它确认成没成——不靠 LLM 自己看图说「做好了」 |
| **编排器**(`src/orchestrator.py`) | 把上面这些串成一个简单的主循环 |

---

## 三、请求处理链路:一条消息从进到出

顶级 agent 的一条共识:**主循环简单到就是个循环,复杂度全在外围**(记忆、验证、安全)。
ANIMA 照这个来——一条用户消息进来,主循环最多转 N 轮(`DEFAULT_MAX_STEPS`),每一轮就是
「**看 → 想 →(过安全闸)→ 动 → 再看**」,直到大脑只出文字 = 收尾。骨架用 **LangGraph** StateGraph
(为未来长出反思/规划等认知节点留好图结构),节点内脏全是自有模块——LLM 层与 MCP 桥不换 LangChain 抽象。

```
   用户发一句话
        │
        ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │ ① 看 perceive   向世界要一帧画面 + 结构化真值        (MCP: resource read) │
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
   │ ④ 动 invoke     把工具调用交给世界执行               (MCP: tools/call)     │
   │      │                                                                  │
   │      └──────── 回到 ① 重新看一眼(闭环纠错)───────────────────────────────┘
```

对应代码 `src/orchestrator.py` 的 `handle()`(整段返回)/ `handle_stream()`(边跑边流式推给前端)。
**工具调用发生在第 ② 步(大脑决定调谁)和第 ④ 步(世界执行)——它怎么实现的,见下面 §五。**

每一轮还会产出一份**结构化轨迹**:这一步看到的图 + ground truth(输入)、想了什么、调了哪些工具(思考)、
最终回复。前端把它做成**两层折叠**,方便排查「它到底看到了什么、怎么想的」。

---

## 四、怎么接入一个世界(AWI 走标准 MCP)

接口采标 **MCP(Model Context Protocol)**:任何「世界」实现成一个标准 **MCP server**(挂在 `/mcp`),
ANIMA 作为 MCP host/client、换个 URL 就能接。世界用 MCP 的三个原语自我描述:

```
Tools    (tools/list, tools/call)      ->  这个世界有哪些高层动作(语言可读,不是关节角),如 move
Resource (resources/read)              ->  anima://observation = 当前画面(png)+ 结构化 state；读一次给一份
Prompt   (prompts/get "guidance")      ->  世界的「说明书」:自我介绍怎么跟它打交道；大脑读它进系统提示
```

**挂载服务(顾问)也是同一种 MCP server**,只是纯计算——只填 Tools,没有 Resource / Prompt。
例:象棋引擎 service(`services/chess_engine_mcp.py`,`best_move`/`evaluate`/`legal_moves`)。
**配对关系写在应用侧**:world 在能力自述里声明配套服务(资源 `anima://services`,如 sim-chess 声明
chess-engine),大脑握手读到就自动连接——大脑不认识任何具体服务,连几百个也不增加认知负荷。

**视频流永远带外**:世界另推一条 `GET /stream`(MJPEG)给网页看——MCP 只跑 JSON-RPC 文本、传不了视频,所以
它和 `GET /health`(探活)、`GET /status`(上帝视角真值,绝不进感知)一样走普通 HTTP,不进 MCP(红线)。
ANIMA 有个 **AWI 仪表盘 `/awi`**,把所有 server(世界 + 引擎)、各自的 tools/state/说明书、实时 MCP 流量都展示出来;
能力在连接时**握手一次后缓存**,流量同时**落盘到 `logs/awi-*.jsonl`** 方便追溯。

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

## 九、下棋:LLM 亲自下每一步(无任何"模式")

下棋不再是一个"模式"——**就是普通对话**。你说「该你了,你执黑」,ANIMA 自己看棋盘截图认局面、
自己从画面和对话历史推出 FEN、自己调引擎顾问 `best_move(fen)` 拿最佳着法、再自己调世界的 `move` 落子、
回你一句话。没有循环、没有技能、没有视觉模块兜底——**读错棋盘就读错,这本身就是对模型能力的测量**
(8B 级小模型基本认不对整盘;演示请用 GPT-5.5 / Claude 这类强脑)。

- **world `sim-chess`**(`world/sim-chess/`):独立棋具——握唯一真值、判合法、渲染棋盘、内置电脑棋手。
  对大脑只暴露一个动作 `move`,perceive 只给画面、state 空 `{}`,绝不给局面/FEN/轮次/胜负。
  它同时**声明配套的 chess-engine 服务**(挂载关系属于应用侧)。
- **service `chess-engine`**(`services/chess_engine_mcp.py`,`:8108`,下棋必起):纯计算顾问,给 FEN
  回最佳着法/评估/合法着;FEN 不合法会报可读错误,让大脑自我修正后重试。
- 一回合的真实链路:看图 → `best_move(fen=自己推的)` → 重新看图 → `move(from,to)` → 出文字。
  全过程在 **Session Logs** 里一条链可查(llm_call → service_call → world_call)。

**跑法**:起 sim-chess 世界 + 引擎服务 + 后端,会话连 sim-chess,聊天里直接说「该你了」:
```bash
# 终端1:棋具世界(独立进程)
cd world/sim-chess && pip install -e . && uvicorn server:app --port 8102
# 终端2:象棋引擎服务(下棋必起;sim-chess 声明了它,大脑会自动连接)
./.venv/bin/uvicorn services.chess_engine_mcp:app --port 8108     # 在 anima-zero 根
# 终端3:后端(默认清单已含全部世界)
uvicorn presentation.server:app --port 8000
# 网页新建会话(世界选 sim-chess)→ 在 sim-chess 网页(:8102)人执白走一步 → 聊天说"该你了,你执黑"
```

## 十、Camera World：让 ANIMA 看真实摄像头(v0.3)

ANIMA 第一次看**真实物理世界**(不再是程序画出来的合成图)。本版很轻:**只能看、能聊、不能操作**——给将来上真机的"眼睛"先把"真摄像头 → 编码 → 喂给视觉大模型"这条链路跑通。

- **world `camera`**(`world/camera/`):把真实 USB 摄像头的实时画面通过 AWI 交给 ANIMA。`capabilities` 的 **tools 是空的** —— ANIMA 在这个世界里**没有任何可执行动作**("只能看、不能操作"是结构上保证的,不是靠提示词)。`perceive` 给当前所选摄像头的真帧 + 极简 state(选了哪个、是否在线);`/invoke` 一律拒绝。
- **摄像头由人来选、来开**:服务启动**不主动打开任何摄像头**,只枚举有哪些。打开哪个,由人在世界页(`localhost:8104`)下拉框里选,插了多个可随时切。
- **脑侧零改动**:零动作世界走的就是主循环现成的"看画面→大模型→出文字"纯聊天路径。

```bash
# 终端1:起摄像头世界(独立进程)
cd world/camera && pip install -e . && uvicorn server:app --port 8104
# 打开 localhost:8104 选一个摄像头 → 画面出现
# 网页新建会话(世界选 camera)→ 问"你看到了什么"→ ANIMA 描述真实画面
```

---

## 十一、接口采标 MCP + 物理世界起步(v0.4)

这一版做两件大事,外加一条诚实的边界。

- **接口从自研 HTTP(AWI)换成业界标准 MCP**:世界＝标准 **MCP server**、脑＝**host**。MCP 三原语 **Tools / Resources / Prompts** 恰好对应我们本来的**动作 / 感知 / 说明书**——`tools/call`＝动作,`resources/read anima://observation`＝感知(画面快照 + 结构 state),`prompts/get "guidance"`＝**说明书**(世界自我介绍怎么跟它打交道,注入脑的系统提示)。世界 server＝三原语齐全的现实;引擎 server＝只有 Tools 的纯计算顾问——同一套协议。下棋引擎独立成一个 MCP server(`:8108`)。
- **第一个物理世界 `gazebo-chess`(`:8106`)**:sim-chess 那张棋桌的 **Gazebo 3D 物理版**,真实建模六轴臂 + 真实夹爪,对大脑只露和 sim-chess 一样的 MCP 接口,内部把 ROS2 + MoveIt + Gazebo 全包起来。v0.4 先跑通 infra(往 Gazebo spawn 棋盘/棋子/相机、读位姿、俯视相机出图、MoveIt 解 IK + 发轨迹让臂动)。
- **teleop 手动遥控(网页 GUI,`:8110`)**:先把「人能顺畅点动这条臂」验通——纯 ROS2(发 `joint_trajectory` 话题)+ MoveIt `/compute_ik` + `joint_trajectory_controller` 插值,平滑的笛卡尔点动。

> **诚实的边界**:ANIMA **自主**走子那条链路(大脑发 `move` → 世界内部解 IK + 夹取 + 搬运 + 放下 + 自检)在 v0.4 会超时,**v0.5 已按框架问题修通**(见下节)。v0.4 交付的是「标准接口 + 物理世界基础设施 + 手动遥控」。

---

## 十二、长动作通信修正 + 视觉桥:ANIMA 在物理世界下棋(v0.5)

这一版先修地基、再长能力。

- **长动作的「生命迹象」语义(框架修正)**:物理动作要几十秒,v0.4 的固定超时会把它误杀,且世界把活儿跑在事件循环上、一次 move 冻住整个世界服务器。v0.5 采标 **MCP progress notifications**:世界把工具执行放到工作线程、分阶段报人话进度(「已夹取,正在移向 e4」);大脑**有进度就续命、失联才判死、另设总上限**,进度实时上 AWI 仪表盘与对弈面板。对任何"慢原子动作"的世界通用。
- **双层视觉桥(大脑读真 3D 盘)**:相机改**斜上方**机位(看得出子型);第一只眼**追踪层**(板角自标定 + 透视矫正 + 逐格采样,只认 空/白/黑——便宜、稳、但盲),第二只眼 **CNN**(逐格 13 类认子型——懂、但会认错,合成数据可复现训练,权重缺失自动降级单层);**裁判三方对账**(两眼互检 × 信念期望)——一致才推进,冲突/看不清一律"再看一眼",绝不静默走错。
- **多子 + 失败补救**:`GZCHESS_SETUP_FEN` 按 FEN 摆多子(棋子分六型剪影,碰撞体不变);失败注入(夹空/放偏,默认关)+ 世界执行自检分类(grip_miss/place_offset/drop + 实际落格)→ 大脑针对性补救(夹空原样重试、放偏从实际落格夹回),每次重试前必重新感知。
- **活体验收**:王兵残局上,ANIMA 经真实斜视相机读盘、真夹真放走子、**纯视觉认出对手挪的子**,4 个半回合信念盘与世界真值完全一致;注入夹空后 检测→补救→走成。

---

## 状态

**v0.5(Pre-alpha),持续迭代中。** v0.1 封版了顶层架构(世界独立 + 会话 + 主循环 + 外围 hook + 原生 tool-calling);
v0.2 长出对弈技能与行为树;v0.3 接入真实摄像头世界 camera;v0.4 接口**采标 MCP** + 物理世界 gazebo-chess;
**v0.5 先修长动作通信语义(MCP progress + 生命迹象等待),随后反向大简化**:删掉整个 game mode
(行为树/技能/视觉栈),下棋回归普通对话、**每一步由 LLM 亲自决定**;端点分成 **world(现实)+
service(顾问,world 声明挂载)** 两类;主循环迁 **LangGraph** 骨架;三套日志统一成按会话的
**Session Logs**。真机安全硬检查、持续响应模式按依赖顺序后做。
`anima-zero` 是完全开源的 Zero 线展示版。

## License

[Apache License 2.0](LICENSE) — Copyright 2026 Jeff Liu Lab
([jeffliulab.com](https://jeffliulab.com),GitHub [@jeffliulab](https://github.com/jeffliulab))。
