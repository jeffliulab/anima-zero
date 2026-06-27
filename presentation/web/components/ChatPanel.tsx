"use client";
import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  getSession,
  imgUrl,
  setSessionBrain,
  streamChat,
  type Brain,
  type ChatEvent,
  type RecMsg,
  type SessionSummary,
} from "@/lib/api";

type ThinkStep = { text: string; tool_calls: { name: string; args: Record<string, unknown> }[]; tool_results: string[] };
type Turn = {
  user?: string;
  inputs: { imageSrc: string | null; state: Record<string, unknown> }[];
  thinking: ThinkStep[];
  reply: string;
  brain?: string; // 这回合由哪个大脑作答(切换大脑后据此插分隔线)
};

// 会话记录(逐条)→ 回合
function groupTurns(msgs: RecMsg[]): Turn[] {
  const turns: Turn[] = [];
  for (const m of msgs) {
    if (m.role === "user") {
      turns.push({ user: m.text, inputs: [], thinking: [], reply: "" });
      continue;
    }
    let t = turns[turns.length - 1];
    if (!t || t.reply) {
      t = { inputs: [], thinking: [], reply: "" };
      turns.push(t);
    }
    if (m.role === "perception") {
      t.inputs.push({ imageSrc: m.image_ref ? imgUrl(m.image_ref) : null, state: m.state });
    } else if (m.role === "assistant") {
      if (m.brain) t.brain = m.brain; // 记下这回合是哪个大脑答的
      if (m.tool_calls && m.tool_calls.length) {
        t.thinking.push({ text: m.text, tool_calls: m.tool_calls.map((tc) => ({ name: tc.name, args: tc.arguments })), tool_results: [] });
      } else {
        t.reply = m.text;
      }
    } else if (m.role === "tool") {
      const last = t.thinking[t.thinking.length - 1];
      if (last) last.tool_results.push(`${m.name}: ${m.content}`);
    }
  }
  return turns;
}

const REPLY_CLASS =
  "inline-block max-w-[88%] rounded-2xl bg-neutral-800 px-3 py-2 text-sm " +
  "[&_p]:my-1 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0 [&_ul]:my-1 [&_ul]:list-disc [&_ul]:pl-5 " +
  "[&_ol]:my-1 [&_ol]:list-decimal [&_ol]:pl-5 [&_code]:rounded [&_code]:bg-neutral-900 [&_code]:px-1";

function TurnView({ turn, open }: { turn: Turn; open: boolean }) {
  const hasBody = turn.inputs.length > 0 || turn.thinking.length > 0 || turn.reply;
  return (
    <div className="space-y-2">
      {turn.user && (
        <div className="text-right">
          <span className="inline-block max-w-[85%] rounded-2xl bg-blue-600 px-3 py-2 text-sm">{turn.user}</span>
        </div>
      )}
      {hasBody && (
        <div className="space-y-1 text-left">
          {turn.inputs.length > 0 && (
            <details open={open} className="rounded-lg bg-neutral-800/50 text-xs">
              <summary className="cursor-pointer px-3 py-1.5 text-neutral-400">👁 看到的画面 + ground truth</summary>
              <div className="space-y-2 px-3 pb-2">
                {turn.inputs.map((inp, j) => (
                  <div key={j}>
                    {inp.imageSrc && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={inp.imageSrc} alt="感知" className="max-h-40 rounded" />
                    )}
                    <pre className="mt-1 overflow-x-auto text-[10px] text-neutral-500">{JSON.stringify(inp.state)}</pre>
                  </div>
                ))}
              </div>
            </details>
          )}
          {turn.thinking.length > 0 && (
            <details open={open} className="rounded-lg bg-neutral-800/50 text-xs">
              <summary className="cursor-pointer px-3 py-1.5 text-neutral-400">💭 思考过程</summary>
              <div className="space-y-1 px-3 pb-2 text-neutral-400">
                {turn.thinking.map((th, j) => (
                  <div key={j}>
                    {th.text && <div className="text-neutral-300">{th.text}</div>}
                    {th.tool_calls.map((tc, k) => (
                      <div key={k} className="text-[11px]">
                        → 调用 <code>{tc.name}</code>({JSON.stringify(tc.args)})
                      </div>
                    ))}
                    {th.tool_results.map((tr, k) => (
                      <div key={k} className="text-[11px] text-neutral-500">　结果:{tr}</div>
                    ))}
                  </div>
                ))}
              </div>
            </details>
          )}
          {turn.reply && (
            <div className={REPLY_CLASS}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{turn.reply}</ReactMarkdown>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// 大脑切换分隔线:一条横线 + 中间一句说明
function Divider({ text }: { text: string }) {
  return (
    <div className="my-1 flex items-center gap-2 text-[10px] text-neutral-500">
      <div className="h-px flex-1 bg-neutral-800" />
      <span className="shrink-0">{text}</span>
      <div className="h-px flex-1 bg-neutral-800" />
    </div>
  );
}

export default function ChatPanel({
  session,
  brains,
  onSessionsChanged,
}: {
  session: SessionSummary | null;
  brains: Brain[];
  onSessionsChanged: () => void;
}) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [live, setLive] = useState<Turn | null>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const reload = useCallback(async () => {
    if (!session) {
      setTurns([]);
      return;
    }
    const full = await getSession(session.id).catch(() => null);
    setTurns(full && full.messages ? groupTurns(full.messages) : []);
  }, [session]);

  useEffect(() => {
    reload();
  }, [reload]);
  useEffect(() => {
    bottomRef.current?.scrollIntoView();
  }, [turns, live, busy]);

  const frozen = session?.status === "frozen";
  const curBrain = brains.find((b) => b.name === session?.brain);

  async function switchBrain(name: string) {
    if (!session) return;
    await setSessionBrain(session.id, name);
    onSessionsChanged();
  }

  async function send() {
    const text = input.trim();
    if (!text || !session || frozen || busy) return;
    setInput("");
    setBusy(true);
    const base: Turn = { user: text, inputs: [], thinking: [], reply: "" }; // 立刻显示我的消息
    setLive(base);
    // 不可变更新:每次都基于 prev 返回带新数组的新 Turn,绝不在 updater 里 mutate。
    // (旧写法 setLive({...lt}) 浅拷贝共享同一个 inputs/thinking 数组,又在 setState 里 push;
    //  React 严格模式会把 updater 跑两遍 → 重复 push / 把上一轮思考串进这一轮。这是「你好却显示 move_pen」的根因。)
    const upd = (fn: (t: Turn) => Turn) => setLive((prev) => fn(prev ?? base));
    try {
      await streamChat(session.id, text, (e: ChatEvent) => {
        if (e.type === "perception")
          upd((t) => ({
            ...t,
            inputs: [...t.inputs, { imageSrc: e.image_b64 ? `data:image/png;base64,${e.image_b64}` : null, state: e.state }],
          }));
        else if (e.type === "thinking")
          upd((t) => ({ ...t, thinking: [...t.thinking, { text: e.text, tool_calls: [], tool_results: [] }] }));
        else if (e.type === "tool_call")
          upd((t) => ({
            ...t,
            thinking: [...t.thinking, { text: "", tool_calls: [{ name: e.name, args: e.args }], tool_results: [] }],
          }));
        else if (e.type === "tool_result")
          upd((t) => {
            if (!t.thinking.length) return t;
            const i = t.thinking.length - 1;
            return {
              ...t,
              thinking: t.thinking.map((th, j) =>
                j === i ? { ...th, tool_results: [...th.tool_results, `${e.name}: ${e.message}`] } : th
              ),
            };
          });
        else if (e.type === "reply") upd((t) => ({ ...t, reply: e.text }));
      });
    } catch {
      upd((t) => ({ ...t, reply: "(连不上后端)" }));
    } finally {
      await reload(); // 用记录里的完整回合替换 live(此后折叠收起)
      setLive(null);
      setBusy(false);
      onSessionsChanged();
    }
  }

  // 大脑名 → 显示名;切换大脑后,在变化处插一条分隔线("开启会话" / "切换为")
  const brainLabel = (n?: string) => brains.find((b) => b.name === n)?.label ?? n ?? "";
  let _lastBrain: string | undefined;
  const seps = turns.map((t) => {
    if (t.brain && t.brain !== _lastBrain) {
      const txt = _lastBrain === undefined ? `使用 ${brainLabel(t.brain)} 开启会话` : `切换为 ${brainLabel(t.brain)}`;
      _lastBrain = t.brain;
      return txt;
    }
    return null;
  });

  return (
    <aside className="flex h-screen flex-col border-l border-neutral-800 bg-neutral-900">
      <header className="border-b border-neutral-800 p-3">
        <div className="mb-2 flex items-center justify-between text-xs">
          <span className="font-medium text-neutral-200">和 ANIMA 对话</span>
          <span className="text-neutral-400">🌐 {session?.world ?? (session ? "纯聊天" : "无会话")}</span>
        </div>
        {session && (
          <div className="flex flex-wrap gap-1.5">
            {brains.map((b) => (
              <button
                key={b.name}
                disabled={frozen}
                onClick={() => switchBrain(b.name)}
                className={`rounded-lg border px-2 py-0.5 text-[11px] ${
                  b.name === session.brain
                    ? "border-blue-600 bg-blue-600 text-white"
                    : "border-neutral-700 text-neutral-300 hover:border-neutral-500"
                } ${b.available ? "" : "opacity-50"}`}
              >
                {b.label}
              </button>
            ))}
          </div>
        )}
        {curBrain && (
          <div className="mt-1.5 text-[10px] text-neutral-500">
            当前大脑:{curBrain.vendor} · {curBrain.label}（{curBrain.model}）
          </div>
        )}
      </header>

      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {!session && <div className="p-4 text-center text-xs text-neutral-500">请在左边新建或选择一个会话</div>}
        {turns.map((t, i) => (
          <Fragment key={i}>
            {seps[i] && <Divider text={seps[i]!} />}
            <TurnView turn={t} open={false} />
          </Fragment>
        ))}
        {live && <TurnView turn={live} open={true} />}
        {busy && !live?.reply && <div className="text-xs text-neutral-500">ANIMA 思考中…</div>}
        <div ref={bottomRef} />
      </div>

      {session &&
        (frozen ? (
          <div className="border-t border-neutral-800 p-4 text-center text-xs text-neutral-500">
            🔒 这个会话已冻结、只读。新建会话可继续。
            <span className="group relative ml-1 cursor-help text-neutral-400">
              ❓
              <span
                className="pointer-events-none invisible absolute bottom-full left-1/2 z-10 mb-1 w-64 -translate-x-1/2
                           rounded-lg bg-neutral-800 p-2 text-left text-[11px] leading-relaxed text-neutral-300
                           opacity-0 shadow-lg transition-opacity group-hover:visible group-hover:opacity-100"
              >
                为保护物理设备的安全:同一个世界一旦开了新会话,原来的会话会立刻被锁定、变成只读——
                你仍可以翻看它的历史轨迹,但它不再接入实时感知系统,也不能再向世界下达动作。
              </span>
            </span>
          </div>
        ) : (
          <div className="flex gap-2 border-t border-neutral-800 p-3">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send()}
              placeholder="给 ANIMA 下达一个指令…"
              disabled={busy}
              className="flex-1 rounded-xl bg-neutral-800 px-3 py-2 text-sm outline-none placeholder:text-neutral-500 disabled:opacity-50"
            />
            <button
              onClick={send}
              disabled={busy}
              className="rounded-xl bg-blue-600 px-4 py-2 text-sm font-medium disabled:opacity-50"
            >
              发送
            </button>
          </div>
        ))}
    </aside>
  );
}
