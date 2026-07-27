// 后端地址。部署到非本机时设环境变量 NEXT_PUBLIC_API;默认连本机 :8000。
//
// ⭐ 空串是有意义的一档，不是"没设"：`npm run build:static` 会用 NEXT_PUBLIC_API="" 构建，
//    于是下面每一处 `${BASE}/api/...` 都变成 `/api/...`——**相对于当前页面的源**。
//    这正是把网页打进 wheel、由后端自己端出来时需要的：用户拿 `anima serve --port 9000`
//    换个端口，页面照样连得上，因为它连的就是"端出它的那个服务"。
//    注意用的是 `??` 不是 `||`：空串必须能穿过去，`||` 会把它当成假值退回 :8000，
//    那样打进 wheel 的页面就会去连一个也许根本没起的 :8000。
const BASE = process.env.NEXT_PUBLIC_API ?? "http://localhost:8000";

// /awi terminal 最多显示多少条 AWI 流量。必须 ≤ 后端缓冲(脑端 awi_log 的 AWI_LOG_MAXLEN=400),否则永远凑不满。
export const AWI_LOG_SHOWN = Number(process.env.NEXT_PUBLIC_AWI_LOG_SHOWN) || 300;

// 前端轮询间隔（毫秒）：集中此处、可用 NEXT_PUBLIC_* env 覆盖，不在各组件内联写死。
export const POLL_AWI_MS = Number(process.env.NEXT_PUBLIC_POLL_AWI_MS) || 3000;

export type Brain = {
  name: string;
  vendor: string; // 厂商:OpenAI / Anthropic / Ollama·本地
  label: string;
  model: string; // 版本号(调 API 用的字符串,如 claude-opus-4-8)
  hosting: "api" | "local"; // 托管:云端 api / 本地 local
  available: boolean;
};

// 流式聊天的事件(SSE)
export type ChatEvent =
  | { type: "start"; brain: string; model: string }
  | { type: "perception"; image_b64: string | null; state: Record<string, unknown> }
  | { type: "thinking"; text: string }
  | { type: "tool_call"; name: string; args: Record<string, unknown> }
  | { type: "progress"; name: string; message: string; progress: number } // 长动作实时进度（如夹爪搬运）
  | { type: "tool_result"; name: string; ok: boolean; message: string }
  // stop_reason 只在这一轮是被闸门收尾时才有：steps=转太多步 / time=跑太久 / interrupt=用户点了停止。
  // LLM 自己出文字收尾时没有这个字段。
  | { type: "reply"; text: string; stop_reason?: "steps" | "time" | "interrupt" }
  | { type: "done" };

// 核心运行参数（左下角显示）。值/env 名/说明都来自后端的 config.Settings，前端不写死任何数字。
export type RuntimeParam = {
  key: string;
  label: string;
  value: number;
  env: string;
  description: string;
};

// trust: "" 表示问不到（世界离线）。unknown = 没审批过；changed = 批准过但清单变了；trusted = 可用。
export type World = { name: string; url: string; online: boolean; trust?: TrustState };

export type TrustState = "" | "unknown" | "changed" | "trusted";

// 一个世界**原样**声明的东西——审批界面看的就是它。
// ⛔ 这是未经信任过滤的原文：给人看的必须和被批准的是同一份，否则这次审批毫无意义。
export type WorldManifest = {
  ok: boolean;
  message?: string;
  state: TrustState;
  reason: string;
  changes: string[];        // state=changed 时：和上次批准的差在哪
  url: string;
  guidance: string;
  tools: { name: string; kind: string; description: string; parameters: unknown }[];
};

export async function getWorldManifest(name: string): Promise<WorldManifest> {
  const r = await fetch(`${BASE}/api/worlds/${encodeURIComponent(name)}/manifest`);
  return (await r.json()) as WorldManifest;
}

export async function approveWorld(name: string): Promise<{ ok: boolean; message: string }> {
  const r = await fetch(`${BASE}/api/worlds/${encodeURIComponent(name)}/approve`, { method: "POST" });
  return (await r.json()) as { ok: boolean; message: string };
}

// 世界的一项可配置项（v1.0 的 AWI 声明通道）。世界声明什么，网页就渲染什么——
// ⛔ 前端不认识任何具体键名（body/相机/…），加新配置项不用改前端。
export type WorldConfigOption = {
  key: string;
  label?: string;
  description?: string;
  value: string;
  choices?: { value: string; label?: string }[];
};

export async function getWorldConfig(name: string): Promise<WorldConfigOption[]> {
  const r = await fetch(`${BASE}/api/worlds/${encodeURIComponent(name)}/config`);
  const j = await r.json();
  return (j.options ?? []) as WorldConfigOption[];
}

export async function setWorldConfig(name: string, key: string, value: string) {
  const r = await fetch(`${BASE}/api/worlds/${encodeURIComponent(name)}/config`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, value }),
  });
  return (await r.json()) as { ok: boolean; message?: string };
}

// 让大脑重新问一遍这个世界有哪些工具。
// 背景：能力清单在首次握手时被缓存，世界加了新工具而后端没重启的话，新工具永远上不了工具单。
export async function refreshWorld(name: string) {
  const r = await fetch(`${BASE}/api/worlds/${encodeURIComponent(name)}/refresh`, { method: "POST" });
  return (await r.json()) as { ok: boolean; message?: string; tools?: string[] };
}

export type SessionSummary = {
  id: string;
  world: string | null;
  brain: string;
  status: "active" | "frozen";
  created_at: string;
  title: string;
  // ANIMA 自己的两个工作记忆通道（它经内建元工具亲自增删；网页只做显示器，不提供编辑）
  core_task: string;   // 一句话：我在干什么
  notes: string[];     // 一条条：我发现了什么
};

// 会话记录里的一条(后端落盘格式)
export type RecMsg =
  | { role: "user"; text: string; ts?: string }
  | { role: "perception"; image_ref: string | null; state: Record<string, unknown>; ts?: string }
  | { role: "assistant"; text: string; tool_calls?: ToolCall[]; brain?: string; ts?: string }
  | { role: "tool"; id: string; name: string; content: string; ts?: string };

export type ToolCall = { id: string; name: string; arguments: Record<string, unknown> };

export type SessionFull = SessionSummary & { messages: RecMsg[] };

export const perceiveUrl = (sessionId: string, tick: number) =>
  `${BASE}/api/perceive?session_id=${encodeURIComponent(sessionId)}&t=${tick}`;

export const imgUrl = (ref: string) => `${BASE}/api/imgfile?ref=${encodeURIComponent(ref)}`;

export async function getBrains(): Promise<Brain[]> {
  const r = await fetch(`${BASE}/api/brains`);
  return ((await r.json()) as { brains: Brain[] }).brains;
}

export async function getWorlds(): Promise<World[]> {
  const r = await fetch(`${BASE}/api/worlds`);
  return (await r.json()) as World[];
}

// ---- AWI 仪表盘(/awi)----
export type AwiTool = { name: string; description: string; kind: string; parameters: unknown };
export type AwiWorld = {
  name: string;
  url: string;
  kind: string;      // "world"（有感知的现实：tools + resource + prompt 三原语齐）
  online: boolean;
  version: string;
  tools: AwiTool[];
  state: Record<string, unknown> | null; // ANIMA 随画面一起经 perceive 收到的结构化状态（world→脑 唯一结构化通道，脑能看）
  status: Record<string, unknown> | null; // 世界自身真实状态，仅人看：走世界本地 /status（人的上帝视角），ANIMA 看不到，如 FEN
  state_schema: Record<string, string>; // 世界【声明】的 perceive.state 契约（键→含义）——面板据此显示，不靠缓存上次 perceive 猜
  guidance: string; // 世界的「说明书」（= MCP prompt）：自我介绍怎么跟它打交道；大脑读它进系统提示，面板第四区显示
  config?: { options?: WorldConfigOption[] }; // 世界声明的可配置项（v1.0 新通道；改它走带外 HTTP，大脑只读）
  trust?: TrustState; // 审批状态（v1.1）。⚠️ 上面的 tools / guidance 是**过滤后**的：
                      // 未批准的世界这两栏是空的，所以这个字段必须和它们一起显示，
                      // 否则看的人只会以为这个世界坏了。
};
// Engine Server（引擎顾问，如棋类引擎）：和 World Server 一样都是标准 MCP server，只是纯计算——
// 只有 tools，无画面(resource)、无说明书(prompt)。由 ANIMA（Host）按 config.services() 挂载
//（标准 MCP 组装：连哪些 server 是 Host 的活，World Server 不声明它、server 之间互不相识）。
export type AwiService = {
  name: string;
  url: string;
  kind: string;      // "service"
  online: boolean;
  tools: AwiTool[];
};
export type AwiOverview = {
  worlds: AwiWorld[];
  services?: AwiService[]; // ANIMA 按配置挂载的服务（顾问）
  brains: Brain[];
  sessions: SessionSummary[];
  stats: { total: number; by_method: Record<string, number>; by_world: Record<string, number> };
};

export async function getAwi(): Promise<AwiOverview> {
  const r = await fetch(`${BASE}/api/awi`);
  return (await r.json()) as AwiOverview;
}

export const awiEventsUrl = () => `${BASE}/api/awi/events`;

// ---- Session Logs（本会话全部行为流水：LLM / 世界 / 服务，按时间合并）----
export const POLL_SESSION_LOGS_MS = Number(process.env.NEXT_PUBLIC_POLL_SESSION_LOGS_MS) || 2000;
type SessionLogBase = {
  id: number;
  t?: number; // unix 秒（合并排序键；旧条目可能没有）
  ts: string;
  session: string; // 这次调用属于哪个会话（空=非会话场景，如连通自检）
};
export type LlmCallEntry = SessionLogBase & {
  kind: "llm_call"; // 脑↔大模型
  model: string;
  system: string; // 系统提示（完整留存）
  last_user: string;
  n_history: number;
  n_tools: number;
  has_image: boolean;
  reply: string;
  tool_calls: string[];
  tokens: { input: number; output: number; total: number } | null; // provider 给的用量，没给则 null
  ms: number;
  error: string;
};
export type WorldCallEntry = SessionLogBase & {
  kind: "world_call"; // 脑↔世界（MCP：capabilities/perceive/invoke/progress）
  world: string;
  method: string;
  summary: string; // 出方向(ANIMA→世界)
  resp: Record<string, unknown>; // 回方向(世界→ANIMA)结构化
  ms: number;
};
export type ServiceCallEntry = SessionLogBase & {
  kind: "service_call"; // 脑↔挂载服务（顾问，如象棋引擎）
  server: string;
  method: string;
  summary: string;
  resp: Record<string, unknown>;
  ms: number;
};
export type SessionLogEntry = LlmCallEntry | WorldCallEntry | ServiceCallEntry;

export async function getSessionLogs(
  limit = 500,
  session = "",
): Promise<{ entries: SessionLogEntry[]; sessions: string[] }> {
  const q = `limit=${limit}` + (session ? `&session=${encodeURIComponent(session)}` : "");
  const r = await fetch(`${BASE}/api/session-logs?${q}`);
  const j = (await r.json()) as { entries: SessionLogEntry[]; sessions?: string[] };
  return { entries: j.entries, sessions: j.sessions ?? [] };
}

export async function listSessions(): Promise<SessionSummary[]> {
  const r = await fetch(`${BASE}/api/sessions`);
  return (await r.json()) as SessionSummary[];
}

export async function getSession(id: string): Promise<SessionFull> {
  const r = await fetch(`${BASE}/api/sessions/${id}`);
  return (await r.json()) as SessionFull;
}

export async function createSession(world: string | null, brain: string): Promise<SessionSummary> {
  const r = await fetch(`${BASE}/api/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ world, brain }),
  });
  return (await r.json()) as SessionSummary;
}

export async function deleteSession(id: string): Promise<void> {
  await fetch(`${BASE}/api/sessions/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function setSessionBrain(id: string, brain: string): Promise<void> {
  await fetch(`${BASE}/api/sessions/${id}/brain`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ brain }),
  });
}

// 叫停这个会话正在跑的那一轮。**立刻返回、不等它真的停**：世界那边正在做的那一步还得做完
// （机器狗要把这步迈完），所以按钮此后显示「停止中…」，直到流自己以停顿语收尾。
// ⛔ 不要改成 AbortController 掐掉 fetch——那只是前端自己捂住眼睛，后端还在跑、还在花钱。
export async function interruptSession(id: string): Promise<void> {
  await fetch(`${BASE}/api/sessions/${encodeURIComponent(id)}/interrupt`, { method: "POST" });
}

// 核心运行参数（左下角常驻显示）。⛔ 只读、且必须现读——前端写死数字必然和 .env 对不上账。
export async function getRuntimeConfig(): Promise<RuntimeParam[]> {
  const r = await fetch(`${BASE}/api/config`);
  return ((await r.json()) as { params: RuntimeParam[] }).params;
}

export async function sendChat(sessionId: string, message: string): Promise<{ reply: string }> {
  const r = await fetch(`${BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message }),
  });
  return (await r.json()) as { reply: string };
}

// 流式聊天:边收边回调每个事件(SSE)
export async function streamChat(
  sessionId: string,
  message: string,
  onEvent: (e: ChatEvent) => void,
): Promise<void> {
  const r = await fetch(`${BASE}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message }),
  });
  const reader = r.body?.getReader();
  if (!reader) return;
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      const line = chunk.split("\n").find((l) => l.startsWith("data: "));
      if (line) {
        try {
          onEvent(JSON.parse(line.slice(6)) as ChatEvent);
        } catch {
          /* ignore */
        }
      }
    }
  }
}
