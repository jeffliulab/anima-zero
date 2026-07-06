# Anima Zero Changelog

ANIMA Zero 版本记录。**版本记录要点：保持简洁，每版只说重点，比如具体改了什么。**（格式参考 [Keep a Changelog](https://keepachangelog.com)）

## [0.7.0] — 开发中

Main: gazebo-chess 世界长出「整盘棋」能力——ANIMA 一句话自主下完一整盘（物理抓放几十手，吃子/易位/升变全走真原语），世界内置裁判与瞬移电脑对手，终局棋谱落档可被 eval 评分。大脑侧零代码改动（只调大 `ANIMA_MAX_STEPS`）——这本身就是对「换世界只换地址、大脑一行不改」承诺的实战检验。

Features:

1. 协议变更：全仓由 Apache-2.0 改为 **AGPL-3.0 + 商业双授权**。AGPL-3.0 要求：把本软件（含修改版）分发出去、装进产品、或**通过网络提供服务**给他人使用时，必须向这些用户按 AGPL 开放对应源码（网络服务条款是它与普通 GPL 的关键区别）；不愿承担此开源义务的闭源商业集成，可联系维护者（jeff.pang.liu@gmail.com）另购商业许可。与依赖 GPL-3 的 python-chess 兼容；≤v0.6.0 的历史版本仍按原 Apache-2.0 可用。
2. gazebo-chess 对局化：世界内置**裁判**（三原语动臂前过合法闸，非法秒拒、臂不动；一手棋按标准拆解表逐原语核对，**全部物理核实后真值才推进**；终局判定 + 棋谱落档含物理失败计数）+ **内置电脑对手**（大脑每凑完一手它瞬移应手、不播报走了哪步——大脑看画面自己认；第三份独立引擎副本，禁与另两份合并）+ 吃子落袋（真夹真搬出棋盘后销毁）+ 网页「开新局」（人类侧复位，不给大脑）。无 FEN 的单演示子模式旧行为原样保留。
3. 几何与抓取对齐真实摆位：格宽 4.5cm、底座轴心到板边 10cm（均为实测默认、env 可覆盖）；抓取姿态改**径向倾斜**（朝远离基座方向倒 15–75°，并修正倾斜时 TCP 从不对准抓取点的旧账）——64 格全可达（v0.5 遗留「h 列整列不可达」就此修复，`scripts/reach_map.py` 一条命令复现可达性地图）；棋子外观换**真实斯汤顿网格**（CC-BY 4.0，来源/许可入仓；碰撞体零改动，抓取物理不用重调）。
4. eval 记分台收 gazebo 对局：按世界分别统计原语成功率与延迟（物理失败与非法走子语义不同、绝不合并），gazebo 落档自带 white/black 归边与 physical_fails 明细。

## [0.6.0] — 2026-07-03

Main: 引擎内聚 + world/service 彻底解耦，服务挂载回归标准 MCP「Host 组装」——面向真机前先把边界理干净。简单来说，Host, Service相互之间都变得独立，Engine Server和Anima Host交流，World Server和Anima Host交流，World Server和Engine Server不再交流。

Features:

1. 三个棋类引擎内核（chess/gomoku/go）搬进 services/boardgame_engine/（原跨仓 importlib 读外部文件，clone 下来起不了）；服务更名 boardgame-engine，chess 三工具就活，go/gomoku 就位待接；外部 3-anima-chess-engine 文件夹删除，仓库自足。
2. 大脑的引擎顾问与 sim-chess 世界的内置电脑对手拆成两份有意独立的副本（chess_engine.py / chess_bot.py，零共享代码、禁去重合并）：关掉引擎服务世界电脑照走，顾问跟着大脑跨身体走。
3. 废除 v0.5 的「world 声明服务（anima://services）」机制，改为大脑按 config.services() 自行挂载（与 worlds() 对称）——对齐 MCP 规范「连哪些 server 是 Host 的职责、server 之间互不相识」；配对靠模型看画面自选工具，不靠结构绑定。
4. 统一 MCP 三层称呼与「专线」模型：server 只有两类——World Server（现实，三原语齐全）和 Engine Server（引擎顾问，只有 Tools）；Host（ANIMA 大脑）给每个 server 各开一条专线即 Client 层（代码里的 RemoteWorld / RemoteService，一条专线只连一个 server），专线负责记地址、握手缓存能力、翻译协议、按角色管超时（world 走生命迹象监督、engine 走短超时问答）并记账，专线之间互不相通=server 隔离的落实。README §四与 /awi 页已按此更新。

## [0.5.0] — 2026-07-03

Main: 大重构——删除 game mode 等人为编排，最小化框架来考察智能：LLM 亲自看画面、亲自决定每一步、亲自调用工具。

Features:

1. 改用LangGraph作为ReAct架构编排的底层框架，不再使用自研naive版ReAct框架。
2. Chess engine改为service；service和world的区别在于：service为anima提供问答帮助（顾问），world接受anima的命令输出（现实）。service由world自己声明（anima://services），anima握手时自动挂载。
3. 删除game mode/行为树/skill整套任务编排：下棋回归普通对话（说"该你了"即可），认盘、算棋、拆步全由LLM当场决策；观察-思考-行动成为唯一主循环。
4. 统一Session Logs：LLM调用、world流量、service调用三类留痕按会话合并为一条流水，前端可按会话查看/一键复制。
5. 多相机一等公民：一次感知可含多张命名画面，前端多路直播并列展示；gazebo-chess升级双相机+可读棋盘（格纹+四边坐标），"拿下去/放上来/放到那儿"语言→动作全链实测通过。

## [0.4.0] — 2026-07-02

Main: 接入gazebo仿真下棋界面，配置遥操teleop并实现末端夹爪的笛卡尔移动。

Features:

1. 不再使用自研HTTP作为AWI，改用MCP server标准。旧的perceive, invoke, guidance体系改为Tools/Resources/Prompts.
2. 下棋引擎不再属于下棋skill，独立为一个MCP server.
3. 新增world: gazebo-chess. 该世界使用Soma Zero的替代机Episode1的模型，构建了Gazebo仿真，并模拟出夹爪和棋子。
4. 实现笛卡尔移动，teleop测试抓取棋子成功。

## [0.3.0] — 2026-06-30

Main: 接入真实摄像头世界camera，让 ANIMA 第一次看到真实的物理世界。这一版是一个轻量级版本，主要测试真实camera的stream。

Features:

1. 添加新的world：camera。可以设置分辨率。
2. 修改下棋skill的一些细节。
3. 调试与界面：anima-logs 调试页修了「按会话查永远空」的会话归属 bug，加一键复制整会话全字段 + 完整展示；前端加亮色主题与切换、把 AWI / anima-logs 改成主页内嵌面板。

## [0.2.0] — 2026-06-30

Main: 新建模拟下棋软件sim-chess，新建下棋skill。梳理agent编排框架。

Features:

1. 添加新的world sim-chess，可以模拟五子棋、国际象棋、围棋等不同棋盘。anima只能看到sim-chess的画面，看不到内部程序信息。
2. 在anima的ux界面添加chess mode，进入chess mode后会进入一个循环的行为树模式。chess mode下用户无需反复对话，anima会持续对弈。
3. 设计human in the loop和eval，做了简单的概念实现。
4. 确认「Orchestrator → Skill →（Skill）Adapter → Behavior Tree → Tools」这条自上而下的抽象层级。
5. 确认 AWI 的三个核心请求——perceive（感知）、invoke（操作）、capabilities（问能力）。

## [0.1.0] — 2026-06-27

Main: ANIMA Zero 首个版本。完全重写框架, 取代更早的 ANIMA O1 原型, 不复用其代码。
Features:

1. 确立「认知与世界分离」的核心架构——ANIMA 作为认知系统只负责思考与决策,World(世界)作为独立实体负责感知与执行,两者通过标准协议 AWI 对接。
2. 定义“World”(世界)概念: world可以是任何独立的实体，比如程序、机器人、环境等。anima通过AWI与world通信并实现操作等。
3. 设计初步的anima聊天ux界面，设立session机制，记忆保存在本地；可以在对话中切换大脑。
4. 实现首个示例world sim-desk，包含一个虚拟桌面、笔、画布等，提供移动笔、绘制、擦除三种能力，用于验证整套协议；通过流式传输将画面传递给anima查看。

## [Anima O1] — Before 2026-06-27

Anima O1是早期的设计版本，在Anima Zero开发中被全部推倒，完全重建，因此不再记录Anima O1的相关内容。Anima O1和早期Soma实践基本确定了System1/System2的路线，为Anima Zero和Soma Zero奠定了思想理论基础。
