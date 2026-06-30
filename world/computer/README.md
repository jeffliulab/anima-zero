# world/computer —— 「操作一台电脑」世界（预留 · 暂不开发）

> ⛔ **预留功能，现在不开发。**
> 这个文件夹**只存放思路**，没有任何可运行代码。**未**注册进 `ANIMA_WORLDS`、默认世界清单、
> README 启动命令或任何前端下拉——所以它**不会出现在世界列表里，也不要去连它**。
> 以后有时间 / 有需求再开发。本文档记录 2026-06-30 一整轮调研讨论定下的方向，供将来接手时直接续上。

---

## 这个世界要干什么（一句话）

让 **ANIMA（唯一的大脑）像人一样操作一台电脑**：只靠**看屏幕**和**想**，输出**按像素坐标的鼠标/键盘动作**，
不读任何网页/界面的内部结构（不碰 DOM）。世界这边只负责「给画面 + 执行动作」，自己不思考。

- world 名字叫 **computer**，强调「被操作的是一台电脑」（浏览器只是这台电脑里跑的一个窗口）。
- 这和 `sim-chess` / `sim-desk` 是**同一套世界契约**：world 是独立进程，对外声明 AWI 能力（tool），
  `render()` 返回画面，脑调用 tool。区别见下方「和现有世界最大的不同」。

---

## 核心结论（今天讨论的落点）

1. **「计算机使用」=两半**：**看**（截图喂脑）+ **做**（把鼠标键盘动作打回去）。
   一个「只输出画面的流」只解决了「看」，**不是** computer use。必须同时有「做」的回程通道。

2. **走纯视觉派，排除 DOM 派**（已拍板）。
   - 排除 DOM 的代价：放弃了「稳」和「省 token」。
   - 换来的好处：能干 DOM 永远干不了的活（验证码、Canvas 游戏、图片、任何没有语义结构的画面），
     且符合 ANIMA「像人一样靠看和想」的本质。
   - 注意：**排除 DOM ≠ 排除 Playwright**。Playwright/CDP 可以只当「按坐标点的笨手」（只用
     `screenshot` + `mouse.click(x,y)`，根本不碰 DOM），那仍是纯视觉。

3. **「看容易、点难」是真实的不对称**：浏览器原生的「输出画面」API（`getDisplayMedia` 屏幕共享、
   `chrome.tabCapture`）天生**单向**——只给画面，没有把点击送回去的口子。所以别走屏幕共享那条。

4. **CDP 把两半用一套协议全包了**（关键发现）：见下方「方案 A」。

5. **grounding（把"我想点这个"翻译成准确像素坐标）是唯一命门**。
   通用大模型单看截图点小目标并不准（ScreenSpot Pro 这类硬榜分数普遍很低）。靠两招兜：
   - **闭环重试**：动作 → 再截图 → 核对有没有按预期变 → 没变就重点/微调。
     （和我们 VLA 下棋的结论一致：纯学习达不到单次高精度，靠"带反馈重试"达标。）
   - **可选感知外挂 OmniParser**：纯视觉（检测+OCR，**不读 DOM**）把截图变成带编号的框，
     让脑选"几号框"而不是裸报坐标，大幅提升点击准确率。它**不是脑也不是世界**，是给脑的"眼"加 buff。

6. **ANIMA 是唯一的脑**：凡是「自带 agent 循环 / 端到端 GUI 模型」的方案，要么整个抛开，要么只取
   其「身体」部分（截图+执行器），把它自带的脑扔掉。绝不能让两个脑抢方向盘（违反 orchestrator 红线）。

---

## 和现有世界最大的不同（务必记住）

`sim-chess` / `sim-desk` 这种世界**持有唯一真值、能判成败**（棋盘真值、终局判定）。
**computer 是「开放世界」，没有内建的「成败 / 唯一真值」裁判**——
一台电脑/一个浏览器没有天然的输赢 oracle。

后果：世界契约里「成败由 world 判」的那块，在这里会**往脑那边漏**——
成败只能靠**脑看画面自己判**（就是上面的闭环重试），或针对**具体任务**定「成功标志」。
这是 computer 世界和棋类世界最根本的结构差别，开发时第一个要想清楚的设计点。

---

## 可选方案（两条路线 + 排除项 + 选配）

### 方案 A：CDP / Playwright-笨手（纯浏览器、可 headless、轻）

world = **一个浏览器**。两半都由 **Chrome DevTools Protocol（CDP）** 一套协议提供：

- **看**：`Page.startScreencast` —— 浏览器自己把一帧帧 JPEG（base64）推给你，可 headless，
  不用扩展、不用 OS 抓屏。或更简单：每一步 `Page.captureScreenshot` 按需截一张。
- **做**：`Input.dispatchMouseEvent` / `Input.dispatchKeyEvent` —— 按 **viewport 的 CSS 像素坐标 (x,y)**
  注入鼠标键盘。一次"点击"= `mousePressed` + `mouseReleased` 两个事件。打字可用 `Input.insertText`。
- **优势**：CDP 注入的事件走浏览器**真正的输入管线，是可信事件（isTrusted = true）**；
  而网页里 JS `element.click()` 造的事件 `isTrusted = false`，有些站点一眼识破。
- **怎么用（草图，不是最终代码）**：
  1. 起 Chrome：`chrome --headless=new --remote-debugging-port=9222`（要看得见就去掉 headless）。
  2. 连 CDP：Python 可用 `pychrome` / 直接 websocket 连 devtools 端点；JS 用 Puppeteer。
     或者干脆用 **Playwright 当笨手**：`page.screenshot()` + `page.mouse.click(x,y)` +
     `page.keyboard.type(...)`，底下就是 CDP，但**只调这几个、不碰 DOM**。
  3. 世界对外声明的 AWI tool ≈ `screenshot / move / click / double_click / drag / scroll / type / key`。
- **适合**：world 就是「一个浏览器」、要轻、要能 headless、要能并发多开。
- **弱点**：scope 只在浏览器里；纯 CDP 的瞬移式点击对「行为反爬」（打分鼠标轨迹）不够像人——
  需要时得自己合成带轨迹的鼠标移动。

### 方案 B：整台电脑（OS 级，最像人、能跨窗口）

world = **一整台（虚拟）桌面**，浏览器只是桌面里跑的一个窗口。

- **看**：截整块屏幕（`mss` / `scrot` / `import`），或用现成沙箱的 `screenshot()`。
- **做**：在**操作系统层面**注入——`xdotool`（`xdotool mousemove x y click 1` / `type` / `key`）
  或 `pyautogui`；坐标系是**屏幕物理像素**。
- **优势**：能点**任何窗口**、最像「人坐在电脑前」（真实光标移动轨迹，对付行为反爬更稳）。
- **怎么用（三种现成底座，按"在不在本地/省不省事"挑）**：
  | 底座 | 是什么 | 取舍 |
  |---|---|---|
  | **自拼 xdotool + mss + Xvfb** | 虚拟显示器 + 手 + 眼，自己拼一个 world 执行器 | 最无依赖、100% 在本地、最合"做对别藏脑"；要自己搭桌面 |
  | **E2B Desktop**（`e2b-dev/desktop`） | 开源 SDK，给一台 Linux+Xfce 桌面 + `screenshot/leftClick/write/press/scroll/launch`，**不带脑** | SDK 最干净最快；**默认跑在 E2B 云上（画面/操作出门到第三方），自托管受限（BYOC 仅 AWS/企业）** |
  | **Screenbox / Daytona** | 开源、**自托管**的虚拟桌面（截图/点击/输入 + noVNC 看着它干） | 全在自己机器上、数据不出门；比自拼省事 |
- **参考实现**：**Anthropic 官方 computer-use demo**（`anthropics/anthropic-quickstarts`，MIT，开源）=
  「Xvfb 桌面 + xdotool 执行器 + agent 循环 + Streamlit」。**留下半截当 world**（桌面 + 执行器），
  **扔掉上半截**（它自带的 agent 循环 + 前端）——那个 agent 循环正是 ANIMA 要替代的脑。
- **适合**：world 是「一整台电脑」、要最像人、要过行为反爬、要跨应用。
- **弱点**：比纯浏览器重；要维护一个桌面环境。

### 排除项（带脑、剥不掉 → 会顶替 ANIMA，别拿来当 world）

- **UI-TARS**：端到端 GUI 大模型，脑即全部，剥不掉。
- **browser-use / Stagehand / Skyvern / 各种 Operator 克隆**：要么 DOM、要么脑焊死在框架里。

### 选配（不是主体）

- **OmniParser**（微软，开源）：纯视觉感知外挂，截图→带编号的框，给脑的"眼"加 buff，提升点击精度。

---

## 接进 ANIMA world 契约的形态（将来开发时）

不管走 A 还是 B，形态都一样，和 `sim-desk` 同一套：

- `world/computer/` 起一个**独立进程**，对外声明 AWI 能力：
  `screenshot`（其实是 render 自带）、`move / click / double_click / drag / scroll / type / key`。
- `render()` = 截图。
- **ANIMA orchestrator 是唯一的脑**；world 不思考、不带 agent 循环。
- 成败：**没有内建裁判**（见上「和现有世界最大的不同」）——靠脑看画面判 + 闭环重试。
- 两条红线照旧：
  1. **坐标必须当场从截图算出来，绝不写死**（"点 480,300 = 登录"是反面教材）。
  2. 即使外挂 OmniParser 帮忙标号，也只是让脑"看得更清"，**不是把界面内部状态喂给脑**——
     保持「脑只读像素」的纯度。

---

## 待决问题（留给将来开发，先别拍）

1. **坐标系映射**：喂给脑的截图分辨率，必须和点回去用的坐标系是**同一套**，否则系统性点偏。
   - Anthropic 建议截图降到 **XGA(1024×768)** 喂模型、坐标再按比例映射回真实像素;
     但 Opus 4.7+ 支持高分辨率视觉（长边 2576px，坐标 1:1）——具体用哪套，**绑定哪个脑时实测**。
   - CDP 的 (x,y) 是 viewport CSS 像素;OS 级的 (x,y) 是屏幕物理像素——别混。
2. **成败裁判**：开放世界没有 oracle，怎么给「具体任务」定成功标志？
3. **grounding 精度方案**：通用脑直接点 vs 外挂 OmniParser vs 其它，落地时评估。
4. **人类式鼠标轨迹**：要不要为「行为反爬」合成带贝塞尔曲线/变速的鼠标移动（A 路线尤其需要）。
5. **隐私 / 数据外发**：云（E2B）省事但画面出门;自托管（Screenbox/Daytona/自拼）数据不出门。按需求定。
6. **A 还是 B**：world 是「一个浏览器」还是「一整台电脑」——决定底座选型。

---

## 一句话给将来的自己

> 想轻、想 headless、就管一个浏览器 → **方案 A（CDP / Playwright 笨手）**。
> 想最像人、跨窗口、整台电脑、要过行为反爬 → **方案 B（OS 级：自拼 xdotool / E2B / Screenbox）**。
> 两条都接同一套 world 契约，脑都是 ANIMA。命门都是 grounding，兜底都是闭环重试。

---

### 参考来源（2026-06-30 调研）

- Anthropic computer-use demo（开源，MIT）: https://github.com/anthropics/anthropic-quickstarts （`computer-use-demo/`）
- Claude computer use 文档: https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use
- CDP Input 域（dispatchMouseEvent/dispatchKeyEvent）: https://chromedevtools.github.io/devtools-protocol/tot/Input/
- CDP Page 域（startScreencast/captureScreenshot）: https://chromedevtools.github.io/devtools-protocol/tot/Page/
- MDN Event.isTrusted: https://developer.mozilla.org/en-US/docs/Web/API/Event/isTrusted
- E2B Desktop（无脑桌面 SDK）: https://github.com/e2b-dev/desktop
- Screenbox（自托管虚拟桌面）: https://screenbox.dev/
- OmniParser（纯视觉感知外挂）: https://github.com/microsoft/OmniParser
- UI-TARS（端到端 GUI 模型，排除项·参考）: https://arxiv.org/html/2501.12326v1
