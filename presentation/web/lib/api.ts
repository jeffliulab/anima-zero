// 后端地址。部署到非本机时设环境变量 NEXT_PUBLIC_API(见 presentation/web/.env.example);默认连本机 :8000。
const BASE = process.env.NEXT_PUBLIC_API ?? "http://localhost:8000";

// /awi terminal 最多显示多少条 AWI 流量。必须 ≤ 后端缓冲(脑端 awi_log 的 AWI_LOG_MAXLEN=400),否则永远凑不满。
export const AWI_LOG_SHOWN = Number(process.env.NEXT_PUBLIC_AWI_LOG_SHOWN) || 300;

// 前端轮询间隔（毫秒）：集中此处、可用 NEXT_PUBLIC_* env 覆盖，不在各组件内联写死。
export const POLL_GAME_STATE_MS = Number(process.env.NEXT_PUBLIC_POLL_GAME_STATE_MS) || 1500;
export const POLL_GAME_EVENTS_MS = Number(process.env.NEXT_PUBLIC_POLL_GAME_EVENTS_MS) || 1200;
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
  | { type: "tool_result"; name: string; ok: boolean; message: string }
  | { type: "reply"; text: string }
  | { type: "done" };

export type World = { name: string; url: string; online: boolean };

export type SessionSummary = {
  id: string;
  world: string | null;
  brain: string;
  status: "active" | "frozen";
  created_at: string;
  title: string;
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
  online: boolean;
  version: string;
  tools: AwiTool[];
  state: Record<string, unknown> | null; // 调试真值（世界本地 /status，人的上帝视角，ANIMA 看不到，如 FEN）
  perceive_state: Record<string, unknown> | null; // ANIMA 随画面一起经 perceive 收到的结构化状态（world→脑 唯一结构化通道）
};
export type AwiOverview = {
  worlds: AwiWorld[];
  brains: Brain[];
  sessions: SessionSummary[];
  stats: { total: number; by_method: Record<string, number>; by_world: Record<string, number> };
};

export async function getAwi(): Promise<AwiOverview> {
  const r = await fetch(`${BASE}/api/awi`);
  return (await r.json()) as AwiOverview;
}

export const awiEventsUrl = () => `${BASE}/api/awi/events`;

// ---- anima-logs（脑↔大模型流量调试页）----
export const POLL_ANIMA_LOGS_MS = Number(process.env.NEXT_PUBLIC_POLL_ANIMA_LOGS_MS) || 2000;
export type AnimaLogEntry = {
  id: number;
  ts: string;
  session: string; // 这次调用属于哪个 session（空=非会话场景，如连通自检）
  model: string;
  system: string; // 系统提示前缀——据此分辨 主循环/意图分类/解说/陪聊
  last_user: string;
  n_history: number;
  n_tools: number;
  has_image: boolean;
  reply: string;
  tool_calls: string[];
  tokens: number | null;
  ms: number;
  error: string;
};
export async function getAnimaLogs(
  limit = 300,
  session = "",
): Promise<{ entries: AnimaLogEntry[]; sessions: string[] }> {
  const q = `limit=${limit}` + (session ? `&session=${encodeURIComponent(session)}` : "");
  const r = await fetch(`${BASE}/api/anima-logs?${q}`);
  const j = (await r.json()) as { entries: AnimaLogEntry[]; sessions?: string[] };
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

export async function sendChat(sessionId: string, message: string): Promise<{ reply: string }> {
  const r = await fetch(`${BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message }),
  });
  return (await r.json()) as { reply: string };
}

// ---- Chess Mode（对弈行为树）----
export type GameEvent = { id: number; ts: string; channel: string; text: string; uci?: string };
export type GameQuestion = { id: number; text: string; options: string[] | null; timeout_s: number | null };
export type GameStatus = {
  display_name: string;
  my_side: string;
  turn: string;
  my_turn: boolean;
  move_count: number;
  finished: boolean;
  paused: boolean; // 暂停中（runner 挂起，不再驱动世界）
  question: GameQuestion | null; // HITL：ANIMA 正等人回答的问题；null=没在问
  exit_reason: string;
  last: string;
};
export type GameState = { active: boolean; status?: GameStatus; events?: GameEvent[] };

export async function getGame(sid: string, since = 0): Promise<GameState> {
  const r = await fetch(`${BASE}/api/game/${encodeURIComponent(sid)}?since=${since}`);
  return (await r.json()) as GameState;
}

export async function startGame(
  sid: string,
): Promise<{ ok: boolean; display_name?: string; message?: string }> {
  const r = await fetch(`${BASE}/api/game/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sid }),
  });
  return await r.json();
}

export async function stopGame(sid: string): Promise<void> {
  await fetch(`${BASE}/api/game/${encodeURIComponent(sid)}/stop`, { method: "POST" });
}

// 下棋区的输入框：把用户的话发进正在跑的对弈循环（认输/不下了→停；否则 ANIMA 回一句）。
export async function sayGame(sid: string, message: string): Promise<{ ok: boolean; reply?: string }> {
  const r = await fetch(`${BASE}/api/game/${encodeURIComponent(sid)}/say`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  return (await r.json()) as { ok: boolean; reply?: string };
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
