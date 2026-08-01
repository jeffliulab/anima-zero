# 常见问题 / 故障排查

<a href="faq.md"><img src="https://img.shields.io/badge/Language-English-2f81f7?style=flat-square" alt="English"></a>
<a href="faq_zh.md"><img src="https://img.shields.io/badge/%E8%AF%AD%E8%A8%80-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-e67e22?style=flat-square" alt="简体中文"></a>

新用户真正会踩的六个坑，每条都是**症状 → 原因 → 怎么办**。
拿不准的时候，第一条命令永远是 `anima doctor`——它就是为这种事存在的。

## 1. 装完 anima-zero，一个世界都没有

**症状**：`anima world list` 是空的；`anima doctor` 说清单为空。

**原因**：正常。v1.1.1 起 wheel 只带大脑——世界是独立的程序，包里一个都不装。

**怎么办**：先跑 `anima demo`——它会起一个随包的迷你世界（八格走廊上的一个点）
并真跑一轮，让你看着整条链路走通。然后去弄一个真实世界：clone 本仓拿 `world/`
下的几个，或照 [AWI 规范](awi-spec-v1_zh.md) 自己写一个
（`src/examples/minimal_world.py` 是给你抄的模板）。

## 2. 我的世界显示 offline

**症状**：`anima world list` 里你的世界旁边写着 `offline`。

**原因**：世界是独立进程——大脑不负责启动它，只连已经在跑的。要么世界没启动，
要么它监听的地址和你登记的不一样。

**怎么办**：先把世界起起来（每个世界的 README 都有一行启动命令，比如
`cd world/sim-chess && pip install -e . && uvicorn server:app --port 8102`——世界有自己的
依赖，那一步 install 不能省），再核对地址：世界自己的
启动日志会打印端口，`.env` 里 `ANIMA_WORLDS` 必须指向同一个。
`curl http://localhost:<端口>/health` 应该回 `{"ok":true}`。

## 3. 大脑不肯用我的世界（not approved）

**症状**：世界在线，但大脑表现得像它没有任何工具；`doctor` 说
"not approved — the brain cannot use it"。

**原因**：这不是 bug，是信任模型在按设计工作。一个世界的工具描述和说明书是
别人写的文本，而它们会进入大脑的系统提示词——所以在一个人亲眼看过并批准之前，
这些东西一律不进大脑。见 [SECURITY.md](../SECURITY.md) §2。

**怎么办**：跑 `anima world add 名字 地址`——它会把这个世界声明的一切摊给你看，
再请你决定。批准绑定的是内容：世界变了样回来，会重新问你一遍。开发自己的世界时，
可以用 `ANIMA_TRUST_ALL=1` 跳过（仅限开发）。

## 4. 我没有 API key，还能玩吗？

**症状**：`anima doctor` 里每个大脑都显示 not configured。

**怎么办**，三条免费路径：
- `anima demo`——会提出帮你拉 **Qwen3-4B-Instruct**（Ollama tag 是 `qwen3:4b-instruct`，
  约 2.5GB，纯 CPU 跑）。它是真会思考的，这是官方的无 key 路径。
- 想用带眼睛的完整网页：装 [Ollama](https://ollama.com/download)，然后
  `ollama pull qwen3-vl:8b`，在大脑下拉里选 `qwen3-vl`。
- **mock brain** 什么都不需要——但它不思考，只把链路走一遍给你看管道。
  它每条回复都会明说这一点。

## 5. 启动时报 "Address already in use"

**症状**：起世界或 `anima serve` 时报端口被占用。

**原因**：另一个副本已经在跑了——最常见的是上一次会话留下来的世界进程。

**怎么办**：用 `lsof -i :<端口>` 找到占用者并停掉；或者给新进程换个端口
（每个世界的 server 都收 `--port`，而地址记在 `ANIMA_WORLDS` 里，不在大脑里）。

## 6. sim-house-nav 找不到场景或机器人

**症状**：导航世界起不来，报缺资产。

**原因**：场景和机器人模型来自伴随仓
[alice-house](https://github.com/jeffliulab/alice-house)。世界默认在
anima-zero 的同级目录找它。

**怎么办**：把 alice-house clone 到 anima-zero 旁边；或者放在任意位置，设
`HOUSENAV_ASSETS_ROOT=/path/to/alice-house` 指过去。
