# 参与贡献 / Contributing

> ANIMA Zero 是一个**开源研究原型**(求职展示 + 教学用)。它是一份个人作品集项目,主要由维护者推进;
> 但欢迎你提 issue、给反馈、或提交小的修复 / 文档改进。参与前请先读 [`README.md`](README.md)(顶层架构)和
> [行为准则](CODE_OF_CONDUCT.md)。

## 先搞清楚这是什么

ANIMA = 具身机器人的「大脑」(System 2,只想不动);它隔着一套 **AWI(Anima World Interface)** 接口去观测、
操作一个独立运行的「世界」(System 1)。框架本身**领域无关**——不写死任何具体世界的知识。详见 README 的
「框架结构」「请求处理链路」「工具调用」三节。

## 本地跑起来

按 README「快速上手」即可,三件一起跑:**世界(`world/sim-desk`)· ANIMA 后端 · 网页**。配置(API key /
本地 Ollama 地址 / 世界清单)见 [`.env.example`](.env.example)。注意 `world/sim-desk` 是 **git 子模块**,
clone 时记得 `git clone --recursive` 或事后 `git submodule update --init`。

## 想加点东西?

- **加一个新世界**:实现 AWI 那四个端点(`/capabilities` `/perceive` `/invoke` `/reset`),在 `.env` 的
  `ANIMA_WORLDS` 里加一行 URL 即可被 ANIMA 连上。框架一行都不用改。参考 [`world/sim-desk`](world/sim-desk)。
- **加一个新大脑(LLM)**:见 [`src/llm/README.md`](src/llm/README.md);多数模型走 OpenAI 兼容口,登记到
  `src/llm/factory.py` 那张表即可。
- **工具(tool)怎么写**:工具是世界在 `/capabilities` 里声明的(名字 + 3~4 句描述写清「何时调 / 何时别调」+
  JSON Schema 参数 + kind),框架以**原生 function-calling** 转给大脑——不要在提示词里手写 JSON。

## 约定

- 代码风格跟着周围现有代码走;改动尽量小而聚焦,一个 PR 只做一件事。
- 改了行为请顺手更新对应的 README / `CHANGELOG.md`。
- **不要**提交密钥、`.env`、本地记忆(`memory/`)、日志(`logs/`)——它们都在 `.gitignore` 里。
- ⚠️ 涉及真机的代码/命令有物理风险,**真机操作一律由在场操作者亲手执行**(见 [`SECURITY.md`](SECURITY.md))。

## 提问 / 报告问题

开一个 issue 即可;安全 / 风险相关见 [`SECURITY.md`](SECURITY.md)。也可邮件联系维护者(邮箱见
[`pyproject.toml`](pyproject.toml) 的 `authors`)。

许可证:本项目以 [Apache License 2.0](LICENSE) 发布;提交贡献即表示同意以同一许可证授权。
