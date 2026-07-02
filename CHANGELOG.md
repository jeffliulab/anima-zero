# Changelog

ANIMA Zero 版本记录。**保持简洁——每版只说重点;具体改了什么,查 git commit。** 格式参考 [Keep a Changelog](https://keepachangelog.com)。

## [0.4.0] — 2026-07-02

Main: 把脑↔世界/引擎的接口从自研 HTTP（AWI）换成业界标准 MCP；并第一次把「世界」从合成画面推进到真实物理仿真——新世界 gazebo-chess（Gazebo 物理棋盘 + 真实六轴臂）跑通了基础设施，配一个网页手动遥控 teleop。注：ANIMA 自主走子（大脑发 move）目前会超时，本版不修，留到 v0.5。

Features:

1. 接口采标 MCP：世界＝标准 MCP server，脑＝host。MCP 三原语 Tools / Resources / Prompts 对应 动作 / 感知 / 说明书；新增「说明书」（prompts/get guidance）注入脑的系统提示。
2. 下棋引擎从下棋 skill 里独立成一个 MCP server（:8108，只有 Tools 的纯计算顾问）；顺带简化 sim-chess 的 state。
3. 新增物理世界 gazebo-chess（:8106）：Gazebo 物理仿真 + 真实机械臂，spawn/位姿/俯视相机出图/MoveIt 解 IK + 发轨迹这条 infra 已通（单子、真实夹爪的完整夹取与失败补救留 v0.5）。
4. teleop 手动遥控（网页 GUI，:8110）：ROS2 + MoveIt IK + joint_trajectory_controller 插值，人可顺畅点动这条臂（关节/笛卡尔/夹爪/回 home）——先把物理底座验通。

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

## [Anima O1]

Anima O1是早期的设计版本，在Anima Zero开发中被全部推倒，完全重建，因此不再记录Anima O1的相关内容。Anima O1和早期Soma实践基本确定了System1/System2的路线，为Anima Zero和Soma Zero奠定了思想理论基础。