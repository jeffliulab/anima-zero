# 参与贡献 / Contributing

<a href="../../../CONTRIBUTING.md"><img src="https://img.shields.io/badge/Language-English-2f81f7?style=flat-square" alt="English"></a>
<a href="CONTRIBUTING.md"><img src="https://img.shields.io/badge/%E8%AF%AD%E8%A8%80-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-e67e22?style=flat-square" alt="简体中文"></a>
<a href="../ja/CONTRIBUTING.md"><img src="https://img.shields.io/badge/%E8%A8%80%E8%AA%9E-%E6%97%A5%E6%9C%AC%E8%AA%9E-bf3989?style=flat-square" alt="日本語"></a>
<a href="../fr/CONTRIBUTING.md"><img src="https://img.shields.io/badge/Langue-Fran%C3%A7ais-8250df?style=flat-square" alt="Français"></a>
<a href="../es/CONTRIBUTING.md"><img src="https://img.shields.io/badge/Idioma-Espa%C3%B1ol-1a7f37?style=flat-square" alt="Español"></a>

> ANIMA Zero 是一个**开源研究原型**(求职展示 + 教学用,MIT,见 [LICENSE](../../../LICENSE))。它是一份个人作品集项目,主要由维护者推进;
> 但欢迎你提 issue、给反馈、或提交小的修复 / 文档改进。参与前请先读 [`README.md`](README.md)(顶层架构)和
> [行为准则](CODE_OF_CONDUCT.md)。

## 先搞清楚这是什么

ANIMA = 具身机器人的「大脑」(System 2,只想不动);它隔着一套 **AWI(Anima World Interface)** 接口去观测、
操作一个独立运行的「世界」(System 1)。框架本身**领域无关**——不写死任何具体世界的知识。详见 README 的
「框架结构」「请求处理链路」「工具调用」三节。

## 本地跑起来

按 README「快速上手」即可,三件一起跑:**世界(`world/sim-chess`)· ANIMA 后端 · 网页**。配置(API key /
本地 Ollama 地址 / 世界清单)见 [`.env.example`](../../../.env.example)。本仓没有子模块,普通 clone
就能拿到全部内容。

## 想加点东西?

- **加一个新世界**:世界就是一个标准 **MCP server**(挂在 `/mcp`),用三类原语说话——**Tools**(能力)、
  **Resources**(感知,`anima://observation`)、**Prompts**(说明书 `guidance`);在 `.env` 的
  `ANIMA_WORLDS` 里加一行 URL 即可被 ANIMA 连上。框架一行都不用改。只能看的世界参考 [`world/camera`](../../../world/camera),
  会动手的参考 [`world/sim-chess`](../../../world/sim-chess),以及 README「怎么接入一个世界」一节。
- **加一个新大脑(LLM)**:见 [`src/llm/README_zh.md`](../../../src/llm/README_zh.md);多数模型走 OpenAI 兼容口,登记到
  `src/llm/factory.py` 那张表即可。
- **工具(tool)怎么写**:工具是世界在 MCP `tools/list` 里声明的(名字 + 3~4 句描述写清「何时调 / 何时别调」+
  JSON Schema 参数 + kind),框架以**原生 function-calling** 转给大脑——不要在提示词里手写 JSON。

## 约定

这些规矩多半是因为**出过一次事**才存在的。它们由 `python scripts/selfcheck.py` 机器执行，CI 每次推送都跑。

- **编排器保持任务无关。** `src/core/orchestrator.py` 不许知道自己在驱动什么游戏、什么任务；
  任务专属的知识属于世界。拿不准就问自己：**换一个世界，这段代码还成立吗？**
- **改「全集」是追加，不是替换。** `ANIMA_WORLDS`、`.env.example`、各种默认清单、README 的表格
  ——加一项**绝不能**弄丢已有的。这是硬规矩，因为它被破过：加一个世界时把另一个从界面里整个挤没了。
- **禁止硬编码。** 路径靠派生或环境变量。可调数字进 `src/config.py` 并带说明，不 inline。
  该由模型判断的——意图、要不要停下、走哪一步——交给模型，绝不用关键词清单替它决定。
- **占位要登记，不许埋。** 非留不可的话，在 PR 里说出来。
- **声称有的测试和能力必须真有。** 注释说"这个有测试守着"而其实没有，和造假数据是同一种谎。
- 代码风格跟着周围现有代码走；改动尽量小而聚焦，一个 PR 只做一件事。
- 改了行为请顺手更新对应的 README / **每一份 CHANGELOG**（英文那份在仓根，中日两份在 `docs/i18n/` 下）。
- **不要**提交密钥、`.env`、本地记忆（`memory/`）、日志（`logs/`）——它们都在 `.gitignore` 里。

### 语言

分法是**按读者**分的，而且是**有意**这么分的：

| 什么 | 语言 |
|---|---|
| **模型**读的——系统提示词、工具描述、世界说明书 | **只有英文。**理由见 `src/prompts.py` |
| **人**读的界面文案 | 中英日三份，保持同步 |
| **人**读的文档——README、本文件、SECURITY、ROADMAP | 上面三种再加法语、西班牙语，都在 `docs/i18n/` 下 |
| 公开 API 的 docstring——`core/awi.py`、各 `awi_mcp.py`、模块头 | 中英两份 |
| 解释「为什么这么写」的内部注释 | **中文，而且这是有意的** |

最后一行是一个**决定**，不是遗漏。那些注释是维护者的思考痕迹，翻译会把它们身上有价值的东西抹平。
它们不妨碍任何人**使用**这个项目；而**扩展**它所需要的东西——契约、说明书、文档——都有多语版本。

### 提交信息

英文在前、中文在后，这样历史整体看上去以英文为主：

```text
type: 英文摘要行

英文正文——改了什么、为什么。

---
中文说明：这次改了什么、为什么这么改。
```

写清**理由**，不要只复述 diff。一条说清"为什么"的 commit，日后的价值远高于复述"改了什么"的那条。
仓库根目录的 `.gitmessage` 就是这个模板——每个 clone 跑一次
`git config commit.template .gitmessage`，之后它会自动填好。

## 自检清单

- [ ] `pytest -q` 过
- [ ] `ruff check .` 过
- [ ] `python scripts/selfcheck.py` 过
- [ ] 动过 README 的话 `python docs/check_readme.py` 过
- [ ] 行为有变 → **每一份** `CHANGELOG`（英文在仓根，中日在 `docs/i18n/` 下）与相关 README 都更新了
- [ ] **你加的守卫，亲眼看它红一次。** 故意把东西弄坏、看着测试变红、再放回去。
      一条没人见过它失败的守卫，就是一条没人知道它有没有用的守卫——这个项目已经抓到过**四条**
      悄悄停止守卫的守卫。

## 真机

⚠️ 涉及真机的代码和命令有物理风险，**跑它的人必须在机器现场**。见 [`SECURITY.md`](SECURITY.md)。

## 提问 / 报告问题

开一个 issue 即可；安全 / 风险相关见 [`SECURITY.md`](SECURITY.md)，尤其是第 2 节「接一个世界是一次信任决定」。也可邮件联系维护者(邮箱见
[`pyproject.toml`](../../../pyproject.toml) 的 `authors`)。

许可证:本项目以 [MIT](../../../LICENSE) 发布。提交贡献即表示你同意你的贡献同样以 MIT 提供。
MIT 本身就允许闭源商用,所以不需要额外的贡献者协议,也没有商业双授权那一套。
许可证沿革(哪个版本受哪套条款约束)见 [NOTICE](../../../NOTICE)。
