"use client";

import { useSyncExternalStore } from "react";

/** 界面语言。中文是母版——**词条以中文原文为 key**。
 *
 *  为什么用原文当 key,而不是 `sidebar.newSession` 这种命名 key:
 *  - 代码里读得懂:`t("新建会话")` 一眼知道显示什么,不用来回翻词表;
 *  - **漏翻自动回落成中文**,而不是在界面上露出 `sidebar.newSession` 这种事故;
 *  - 省掉"给两百条文案起名字"这一步——那一步既费时又容易起重名。
 *  代价是长文案当 key 略笨重,以及**同一句中文在不同语境要不同英文时会撞车**。
 *  ⚠️ 真撞过一次:「感知」既是聊天里那张图的 alt,又是 AWI 面板里的协议通道名,
 *     前者该译 perception frame、后者该译 Observation。**解法是把中文改具体**
 *     (alt 改成「感知画面」),而不是在这里发明 key 前缀——中文本来就该写清楚。
 *
 *  ⛔ 只翻**用户看得见**的东西。类型定义上的行尾注释、开发者注释一律不进这里。
 */
export type Lang = "zh" | "en";

const STORAGE_KEY = "anima-lang";

// ─────────────────────────────────────────────────────────────── 词条（中 → 英）
// 没收录的串按原文显示(中文)。加新文案时:先写中文,再来这里补一条英文。
const EN: Record<string, string> = {
  // ---- 世界信任审批（v1.1）----
  // ⚠️ 加了新的 t("…") 就必须同时加这里的英文条目：查不到会**静默回退中文**，
  //    于是英文界面里冒出一段中文，而没有任何东西会报错。
  "(没有描述)": "(no description)",
  "(没有说明书)": "(no guidance)",
  "⚠ 这个世界和你上次批准时不一样了": "⚠ This world is not what you approved last time",
  "⚠ 这个世界还没有被批准": "⚠ This world has not been approved",
  "会改变世界": "changes the world",
  "会被拼进大脑的系统提示词": "goes into the brain’s system prompt",
  "变了什么": "What changed",
  "只批准你信任的世界": "Only approve worlds you trust",
  "只读": "read-only",
  "在你批准之前，它的工具和说明书不会进入大脑——所以现在它列得出来，但驱动不了。": "Until you approve it, its tools and guidance do not reach the brain — so it lists here, but nothing can drive it.",
  "处理中…": "Working…",
  "字": "characters",
  "它声明的动作": "The actions it declares",
  "它的能力清单变了。改动内容在下面；确认无误再重新批准。": "Its manifest has changed. What changed is below; approve again once you are satisfied.",
  "它的说明书": "Its guidance",
  "我看过了，批准它": "I have read it — approve",
  "我看过了，重新批准": "I have read it — approve again",
  "收起": "Collapse",
  "看看它声明了什么": "See what it declares",
  "读取中…": "Loading…",
  // ── 侧栏 ──
  "新建会话": "New session",
  "主页": "Home",
  "回到主页（留白）": "Back to home",
  "连接哪个世界": "Connect a world",
  "用哪个大脑": "Pick a brain",
  "纯聊天": "Chat only",
  "纯聊天 / 不连世界": "Chat only / no world",
  "创建": "Create",
  "取消": "Cancel",
  "还没有会话,点上面新建。": "No sessions yet — create one above.",
  "删除会话": "Delete session",
  "删除这个会话?(不可恢复)": "Delete this session? This cannot be undone.",
  "🔒只读": "🔒 read-only",
  "AWI 仪表盘": "AWI dashboard",
  "运行参数": "Runtime limits",
  "创建会话": "Create session",
  "未配置": "not configured",
  // 运行参数面板的四项(值与说明由后端 /api/config 现读,这里只翻标签)
  "单轮步数上限": "Max steps per turn",
  "单轮时长上限(秒)": "Max seconds per turn",
  "上下文预算(token)": "Context budget (tokens)",
  "笔记本容量(条)": "Notebook capacity",

  // ── 主题 / 语言切换 ──
  "切换到浅色主题": "Switch to light theme",
  "切换到深色主题": "Switch to dark theme",
  "切换深色 / 浅色主题": "Toggle dark / light theme",
  "切换到英文界面": "Switch to English",
  // 切到中文的提示故意保留中文——按钮提供的是"切到那个语言",用目标语言写才不歧义
  "切换到中文界面": "Switch to Chinese（中文）",
  "界面语言": "Interface language",

  // ── 传感区 ──
  "👁 ANIMA 看到的画面": "👁 What ANIMA sees",
  "🎥 第三视角 · 只有你看得到，ANIMA 看不到": "🎥 Third-person — for you only, ANIMA cannot see this",
  "世界实时画面": "Live view from the world",
  "纯聊天 / 未连接世界": "Chat only / no world connected",
  "全部": "All",
  "默认": "default",
  "重试": "Retry",
  "重试连接": "Retry connection",
  "未连接到世界「{name}」": "Not connected to world “{name}”",
  "收不到这个世界的画面。请确认它的进程已启动(见项目根目录的": "No video from this world. Make sure its process is running (see",
  "),起好后点下面重试。": ") and then retry below.",
  "运行命令.md": "the run-commands doc",
  "传感区": "Sensors",
  "实时": "live",

  // ── 对话区 ──
  "和 ANIMA 对话": "Talk to ANIMA",
  "无会话": "no session",
  "展开思考": "Expand reasoning",
  "折叠思考": "Collapse reasoning",
  "一键展开 / 折叠所有回合的思考过程": "Expand / collapse the reasoning of every turn",
  "当前大脑": "Brain",
  "给 ANIMA 下达一个指令…": "Give ANIMA an instruction…",
  "发送": "Send",
  "停止": "Stop",
  "停止中…": "Stopping…",
  "停止生成": "Stop generating",
  "只读:这个会话已冻结(同一个世界同时只允许一个活跃会话)。": "Read-only: this session is frozen (one active session per world).",
  "看到的画面 + ground truth": "Frame seen + ground truth",
  "思考过程": "Reasoning",
  "步": "steps",
  "笔记本": "Notebook",
  "核心任务": "Core task",
  "正在做": "Doing",
  "（还没记笔记）": "(no notes yet)",
  "👁 看到的画面 + ground truth": "👁 Frame seen + ground truth",
  "感知画面": "perception frame",
  "💭 思考过程": "💭 Reasoning",
  "→ 调用": "→ calls",
  "结果:": "result: ",
  "(连不上后端)": "(cannot reach the backend)",
  "使用 {brain} 开启会话": "Session started with {brain}",
  "切换为 {brain}": "Switched to {brain}",
  "请在左边新建或选择一个会话": "Create or pick a session on the left",
  "正在收尾——当前这一步做完就停…": "Wrapping up — it will stop once this step finishes…",
  "ANIMA 思考中…": "ANIMA is thinking…",
  "查看子页面中 · 对话暂不可用（后续开放）": "Viewing a sub-page — chat is unavailable here",
  "🔒 这个会话已冻结、只读。新建会话可继续。": "🔒 This session is frozen and read-only. Create a new one to continue.",
  "为保护物理设备的安全:同一个世界一旦开了新会话,原来的会话会立刻被锁定、变成只读——你仍可以翻看它的历史轨迹,但它不再接入实时感知系统,也不能再向世界下达动作。": "A safety rule for physical hardware: opening a new session on a world immediately locks the previous one. You can still read its history, but it no longer receives live perception and cannot command the world.",
  "这一轮跑完再发下一句…": "Wait for this turn to finish…",
  "停止这一轮（当前这一步做完就停，说「继续」可接着来）": "Stop this turn (it finishes the current step; say “continue” to resume)",
  "ANIMA 自己记的，不随对话变长被遗忘；网页只读。点击展开/折叠": "ANIMA writes these itself; they survive a long conversation. Read-only here — click to expand/collapse.",

  // ── AWI 仪表盘 ──
  "AWI 仪表盘 · 世界与服务": "AWI dashboard · worlds & services",
  "在线": "online",
  "离线": "offline",
  "刷新": "Refresh",
  "重新握手": "Re-handshake",
  "世界": "Worlds",
  "服务": "Services",
  "身体": "Body",
  "配置": "Config",
  "说明书": "Guidance",
  "动作": "Tools",
  "感知": "Observation",
  "状态": "Status",
  "schema / 内容": "schema / content",
  "(无)": "(none)",
  "个能力": "capabilities",
  "图片": "image",
  "字节 · 回程 state:": "bytes · returned state:",
  "带 data": "with data",
  "World Server · ANIMA 栖身的现实": "World Server · the reality ANIMA inhabits",
  "Engine Server · ANIMA 请教的引擎顾问（纯计算）": "Engine Server · a pure-computation advisor ANIMA consults",
  "这个世界的场地配置（世界经 AWI 声明；⚠️ 由你来改，ANIMA 只被告知现状、改不了）": "How this world is set up (declared over AWI; ⚠️ you change it — ANIMA is only told the current state and cannot change it)",
  "ANIMA 可调用的工具（会改世界的过安全闸）": "Tools ANIMA can call (world-changing ones pass the safety gate)",
  "ANIMA 的感知：画面快照 + 结构 state": "What ANIMA perceives: a frame snapshot + structured state",
  "世界的说明书：写给大脑的自我介绍（读进系统提示）": "The world's guidance: how it introduces itself to the brain (read into the system prompt)",
  "world 的场外信息，anima 看不到（仅人看，不走 MCP）": "Out-of-band world info ANIMA cannot see (for humans only, not over MCP)",
  "(无动作，只能看)": "(no actions — observation only)",
  "(离线，拿不到)": "(offline — unavailable)",
  "(离线，拿不到工具清单)": "(offline — tool list unavailable)",
  "(没有声明工具)": "(no tools declared)",
  "(此世界没提供说明书)": "(this world provides no guidance)",
  "(这个世界没有 /status)": "(this world has no /status)",
  "🔒 调试真值（人的上帝视角，如 FEN/棋子真实位置）：": "🔒 Ground truth for debugging (the human's god view):",
  "正在切换…（世界要重建，可能要几秒）": "Switching… (the world is being rebuilt, this takes a few seconds)",
  "连不上后端": "Cannot reach the backend",
  "已切换": "Switched",
  "没成功": "Failed",
  "重新握手中…": "Re-handshaking…",
  "世界那边改了工具或重启了，点这个让大脑重新问一遍（能力清单是握手时缓存的）": "If the world changed its tools or restarted, click this to make the brain ask again (the capability list is cached at handshake)",
  "问答拿反馈：给它编码好的问题，它回答案": "Ask and get an answer: give it a well-formed question, it replies",
  " · 由 ANIMA 按配置挂载（Host 组装）": " · mounted by ANIMA from its own config (standard MCP host assembly)",
  "AWI 仪表盘 · Anima World Interface": "AWI dashboard · Anima World Interface",
  "Session Logs（行为流水）": "Session Logs (activity trace)",
  "← 回主界面": "← Back to the app",
  "大脑接口(LLM)": "Brain interface (LLM)",
  "会话": "Sessions",
  "ANIMA（Host）连接两类 MCP server：": "ANIMA (the host) connects to two kinds of MCP server: ",
  "——它栖身的现实（有画面，动作会改变现实）；": " — the reality it inhabits (it has a camera; actions change that reality); ",
  "——它请教的引擎顾问（纯计算，问答拿反馈，由 ANIMA 按配置挂载）。": " — advisors it consults (pure computation, question in / answer out, mounted by ANIMA from its own config).",
  "这页展示这些连接的契约与实时流量；要看「ANIMA 看到什么→想了什么→调了什么」的完整链，去": "This page shows the contract and live traffic of those connections. For the full chain of what ANIMA saw, thought and called, see",
  "这页怎么读（MCP 细节，点开看）": "How to read this page (MCP details — click to open)",
  "读一次给一份": "one read, one snapshot",
  "世界给大脑看的东西：画面快照(png) + 结构 state（下面是 state 里有什么；绝不含棋盘真值）。": "What the world shows the brain: a frame snapshot (png) plus structured state (listed below — never ground truth).",
  "调用总数": "Total calls",
  "· ANIMA 栖身的现实，每个会话连一个": "· the reality ANIMA inhabits — one per session",
  "· ANIMA 请教的引擎顾问，由 ANIMA 按配置挂载（Host 组装）": "· advisors ANIMA consults, mounted from its own config (host assembly)",
  "(暂无——ANIMA 的服务清单 config.services() 为空)": "(none — ANIMA's service list config.services() is empty)",
  "实时流量": "Live traffic",
  "· ANIMA ↔ World/Engine Server 的每次调用（走 MCP）": "· every call between ANIMA and a World/Engine Server (over MCP)",
  "→ 发出": "→ sent",
  "← 返回": "← returned",
  "每条两半：": "Two halves per line: ",
  "（命令+参数）、": " (command + arguments), ",
  "（图片字节数、成败、回程 state、答案）。": " (image bytes, success/failure, returned state, answer).",
  "(暂无流量;去主界面发条消息,或在世界自己的界面里操作一下)": "(no traffic yet — send a message in the app, or poke the world in its own UI)",
  "(⚠ 疑似夹带棋盘真值)": "(⚠ looks like it leaked ground truth)",
  "(未见棋盘真值 ✓)": "(no ground truth found ✓)",
  "· 带 data": " · with data",

  // ── Session Logs ──
  "Session Logs · 按会话看全链路": "Session Logs · one trace per session",
  "复制整会话": "Copy whole session",
  "已复制": "Copied",
  "选择会话": "Pick a session",
  "暂无流水": "No traffic yet",
  "其它": "other",
  "（无）": "(none)",
  "（无会话）": "(no session)",
  "含截图": "with frame",
  "无截图": "no frame",
  "会话：": "Session: ",
  "输入": "in",
  "输出": "out",
  "合计": "total",
  "上下文": "context",
  "条 · 可用工具": "entries · tools",
  "个 · ": " · ",
  " · 耗时": " · took",
  "用户：": "User: ",
  "回复：": "Reply: ",
  "工具调用：": "Tool calls: ",
  "错误：": "Error: ",
  "system 提示：": "System prompt: ",
  "发出：": "Sent: ",
  "返回：": "Returned: ",
  "已删除": "deleted",
  "全部（合并所有会话）": "All (every session merged)",
  "条": "entries",
  "把当前所列的全部日志（含每个信息要素）复制到剪贴板": "Copy every listed log entry (all fields) to the clipboard",
  "已复制 ✓": "Copied ✓",
  "复制全部日志": "Copy all logs",
  "全部行为流水（合并所有会话）": "All activity (every session merged)",
  "（未选会话）": "(no session selected)",
  "本会话的全部行为流水，按时间合并：": "Everything this session did, merged by time:",
  "LLM 调用（想）": "LLM calls (thinking)",
  "世界往返（看/动，MCP）": "world round-trips (see / act, MCP)",
  "服务调用（问顾问，如引擎）": "service calls (asking an advisor, e.g. the engine)",
  "——「ANIMA 看到什么、想了什么、调了什么」一条链看全。": "— one chain showing what ANIMA saw, thought, and called.",
};

// ─────────────────────────────────────────────────────── 极简语言 store（无第三方库）
// 为什么自己写:整个应用只有一个全局标量(当前语言),用 useSyncExternalStore 订阅足够了。
// 引一个 i18n 框架反而要装 provider、配 namespace、处理 SSR 水合——不值当。
// 预渲染阶段（SSR / 静态导出）拿不到 localStorage 和 navigator，只能先按一个值渲染。
// v1.1 起这个值是 en 而不是 zh：静态导出的 HTML 是随 wheel 分发、也是别人截图会看到的那一份，
// 面向全球社区它该是英文。中文用户会在水合前看到极短一瞬的英文——两边总有一边要闪，
// 而**默认那一边**应该是受众更广的那个。用户自己选过语言之后就再也不闪（走 localStorage）。
// 预渲染与首帧的默认语言，两处共用这一个常量（见 useI18n 里那条注释）。
const INITIAL_LANG: Lang = "en";
let current: Lang = INITIAL_LANG;
const listeners = new Set<() => void>();

function read(): Lang {
  if (typeof window === "undefined") return INITIAL_LANG;
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "en" || saved === "zh") return saved;   // 用户自己选过 → 听他的
  } catch {
    /* 隐私模式等读不了,往下走浏览器语言 */
  }
  // 没选过 → 跟随浏览器语言：中文环境给中文,其余一律英文。
  // (这是常规做法,不是为了截图开的后门——英文用户第一次打开不该看到一屏中文。)
  const nav = typeof navigator !== "undefined" ? navigator.language : "";
  return nav.toLowerCase().startsWith("zh") ? "zh" : "en";
}

// 首次在浏览器里加载时对齐一次真实偏好（SSR 阶段拿不到 localStorage，先按 INITIAL_LANG 渲染）
if (typeof window !== "undefined") current = read();

export function getLang(): Lang {
  return current;
}

export function setLang(next: Lang): void {
  if (next === current) return;
  current = next;
  try {
    localStorage.setItem(STORAGE_KEY, next);
  } catch {
    /* 存不了也照样切，只是刷新后回到默认 */
  }
  document.documentElement.lang = next === "en" ? "en" : "zh-CN";
  listeners.forEach((fn) => fn());
}

function subscribe(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** 翻译一条文案。`vars` 用来填 `{name}` 这类占位符。
 *  查不到就原样返回——**漏翻只是显示中文，不会显示 key**。 */
export function translate(zh: string, lang: Lang, vars?: Record<string, string | number>): string {
  let out = lang === "en" ? EN[zh] ?? zh : zh;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) out = out.replaceAll(`{${k}}`, String(v));
  }
  return out;
}

/** 给**非组件**代码用的翻译（普通函数、事件回调里没法调 hook）。
 *  ⚠️ 它不订阅语言变化——但调用它的那个组件会因为自己用了 useI18n 而重渲染，
 *  重渲染时这个函数被重新执行、读到的就是新语言。所以实际表现是对的。
 *  能用 useI18n 的地方就别用它。 */
export function tt(zh: string, vars?: Record<string, string | number>): string {
  return translate(zh, getLang(), vars);
}

/** 组件里这样用：`const { t, lang, setLang } = useI18n();` 然后 `t("新建会话")`。
 *  语言一变,所有用到这个 hook 的组件自动重渲染。 */
export function useI18n() {
  // ⚠️ 第三个参数是**服务端快照**，预渲染（SSR / 静态导出）用的就是它。
  //    它必须和文件上方那个 `current` 的初值一致——两处都是"还不知道用户偏好时用什么"。
  //    v1.1 改默认语言时只改了上面那一处、漏了这里，结果静态导出的 HTML 仍是中文：
  //    一个默认值散在两个地方，就一定会有人只改一个。
  const lang = useSyncExternalStore(subscribe, getLang, () => INITIAL_LANG);
  return {
    lang,
    setLang,
    t: (zh: string, vars?: Record<string, string | number>) => translate(zh, lang, vars),
  };
}
