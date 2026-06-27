// 后端地址。部署到非本机时设环境变量 NEXT_PUBLIC_API(见 presentation/web/.env.example);默认连本机 :8000。
const BASE = process.env.NEXT_PUBLIC_API ?? "http://localhost:8000";

// /awi terminal 最多显示多少条 AWI 流量。必须 ≤ 后端缓冲(脑端 awi_log 的 AWI_LOG_MAXLEN=400),否则永远凑不满。
export const AWI_LOG_SHOWN = 300;

export type Brain = {
  name: string;
  vendor: string; // 厂商:OpenAI / Anthropic / Ollama·本地
  label: string;
  model: string; // 版本号(调 API 用的字符串,如 claude-opus-4-8)
  kind: "api" | "local";
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
  state: Record<string, unknown> | null;
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
