# Changelog

ANIMA Zero 版本记录。**保持简洁——每版只列重点;具体变更项请查 git commit。** 格式参考 [Keep a Changelog](https://keepachangelog.com)。

## [0.1.0] — 2026-06-27

Main: 最轻量具身 agent 框架封版——脑(System 2)隔着 AWI 接口指挥独立运行的「世界」(System 1)。

Features:
1. **AWI(Anima World Interface)**:脑↔世界接口标准(`/capabilities` `/perceive` `/invoke` `/reset`),换世界 = 换 URL。
2. **通用主循环**:看→想→过安全闸→动→再看;**原生 tool-calling**(工具走 API tools 参数,不在提示词写 JSON)。
3. **会话**:按世界单活 + 冻结;本地记忆;可中途换脑(5 个看图大脑,含本地 Ollama)。
4. **外围件**:确定性安全闸、滑窗上下文、结构化轨迹、`/awi` 仪表盘 + 流量落盘、能力握手缓存。
5. **示例世界 sim-desk**(桌面 + 笔 + 画布,工具 move_pen / draw / erase)+ 三栏网页。

Notes: Pre-alpha,1.0 前接口可能变;取代更早的 ANIMA O1(L0–L5)原型,不复用其代码。

## [0.1.0-pre] — 2026-06-25

Main: 重构起点——虚拟桌面骨架(内部里程碑,未发布)。
