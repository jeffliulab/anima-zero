"use client";
import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { useI18n } from "@/lib/i18n";
import {
  getSession,
  imgUrl,
  interruptSession,
  setSessionBrain,
  streamChat,
  type Brain,
  type ChatEvent,
  type RecMsg,
  type SessionSummary,
} from "@/lib/api";

// 思考区的最大高度：长回合可能几十步，不限高的话思考会把最终回复顶出屏幕、还得手动往下翻。
// 限高 + 内部滚动 + 自动贴底 = 一眼看得到最新一步，同时最终回复始终在视野里。
const THINKING_MAX_H = "max-h-72";

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

function TurnView({ turn, open, live = false }: { turn: Turn; open: boolean; live?: boolean }) {
  const { t } = useI18n();
  const hasBody = turn.inputs.length > 0 || turn.thinking.length > 0 || turn.reply;
  // 正在跑的那一轮：每来一步就把思考区滚到底，像看思维链一路往下长。
  const thinkRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (live && thinkRef.current) thinkRef.current.scrollTop = thinkRef.current.scrollHeight;
  }, [live, turn.thinking.length, turn.thinking[turn.thinking.length - 1]?.tool_results.length]);
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
              <summary className="cursor-pointer px-3 py-1.5 text-neutral-400">{t("👁 看到的画面 + ground truth")}</summary>
              <div className="space-y-2 px-3 pb-2">
                {turn.inputs.map((inp, j) => (
                  <div key={j}>
                    {inp.imageSrc && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={inp.imageSrc} alt={t("感知画面")} className="max-h-40 rounded" />
                    )}
                    <pre className="mt-1 overflow-x-auto text-[10px] text-neutral-500">{JSON.stringify(inp.state)}</pre>
                  </div>
                ))}
              </div>
            </details>
          )}
          {turn.thinking.length > 0 && (
            <details open={open} className="rounded-lg bg-neutral-800/50 text-xs">
              <summary className="cursor-pointer px-3 py-1.5 text-neutral-400">
                {t("💭 思考过程")} · {turn.thinking.length} {t("步")}
              </summary>
              <div ref={thinkRef} className={`space-y-1 overflow-y-auto px-3 pb-2 text-neutral-400 ${THINKING_MAX_H}`}>
                {turn.thinking.map((th, j) => (
                  <div key={j} className="flex gap-1.5">
                    {/* 步号：长回合几十步，得能一眼说出"卡在第几步"，也方便对照 Session Logs */}
                    <span className="shrink-0 tabular-nums text-neutral-600">{j + 1}.</span>
                    <div className="min-w-0 flex-1">
                      {th.text && <div className="text-neutral-300">{th.text}</div>}
                      {th.tool_calls.map((tc, k) => (
                        <div key={k} className="text-[11px]">
                          {t("→ 调用")} <code>{tc.name}</code>({JSON.stringify(tc.args)})
                        </div>
                      ))}
                      {th.tool_results.map((tr, k) => (
                        <div key={k} className="text-[11px] text-neutral-500">　{t("结果:")}{tr}</div>
                      ))}
                    </div>
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

// 停止图标（实心方块，和 ChatGPT 一个语汇）
function StopIcon() {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" fill="currentColor" aria-hidden="true">
      <rect width="10" height="10" rx="1.5" />
    </svg>
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

// 笔记区最大高度：够看四五条，再多在里面滚——它是对话的配角，不许把对话挤下去。
const NOTES_MAX_H = "max-h-40";

// ANIMA 自己的两个状态寄存器，钉在对话顶上（v1.0；v1.0.1 从侧栏挪来）。
//
// **为什么在这儿**：它们是「这场对话的状态」，属于当前会话、不属于整个应用——
// 原先摆在侧栏底部那堆全局项（运行参数 / AWI 仪表盘 / 外观）里，看着像是全局的东西，
// 而且离它所属的那个会话行隔了半个屏幕。钉在对话上方还有个好处：**不随消息滚走**，
// 长回合里始终看得见它在干什么。
//
// **两个寄存器不是一回事，所以分开显示**：
//   核心任务 = 一句话「我在干什么」，LLM 自己 set/clear，实测多为「一轮建、做完清」；
//   笔记本   = 一条条「我发现了什么」，只增删不改写。
// （曾经给这两样起过一个总称叫「工作记忆」——那个词代码里根本没有，反而让人以为是第三样东西，已弃用。）
//
// ⛔ 网页只做显示器、不提供编辑：能被人改的记忆就不是它自己的记忆了。
// 刷新时机：每轮结束（onSessionsChanged）。回合进行中想看实时的，思考流里 add_note 是逐条显示的。
function Notebook({ session }: { session: SessionSummary | null }) {
  const { t } = useI18n();
  const task = session?.core_task ?? "";
  const notes = session?.notes ?? [];
  const [open, setOpen] = useState(false);
  if (!task && !notes.length) return null;
  return (
    <div className="border-b border-neutral-800 bg-neutral-900/40 px-3 py-1.5 text-[11px]">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-1.5 text-left text-neutral-500 hover:text-neutral-300"
        title={t("ANIMA 自己记的，不随对话变长被遗忘；网页只读。点击展开/折叠")}
      >
        <span className={`transition-transform ${open ? "rotate-90" : ""}`}>›</span>
        {task ? (
          <span className="min-w-0 flex-1 truncate">
            <span className="text-neutral-600">{t("正在做")} </span>
            <span className="text-neutral-300">{task}</span>
          </span>
        ) : (
          <span className="flex-1 text-neutral-600">{t("笔记本")}</span>
        )}
        {!!notes.length && (
          <span className="shrink-0 tabular-nums text-neutral-600">📓 {notes.length}</span>
        )}
      </button>
      {open && (
        <div className={`mt-1.5 space-y-1 overflow-y-auto ${NOTES_MAX_H}`}>
          {task && (
            <div className="rounded bg-neutral-800/60 px-2 py-1 leading-snug text-neutral-300">
              <span className="text-neutral-600">{t("核心任务")} </span>
              {task}
            </div>
          )}
          {!notes.length && <div className="text-neutral-600">{t("（还没记笔记）")}</div>}
          {notes.map((n, i) => (
            <div key={i} className="flex gap-1.5 leading-snug">
              <span className="shrink-0 tabular-nums text-neutral-600">{i + 1}.</span>
              <span className="text-neutral-400">{n}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ChatPanel({
  session,
  brains,
  onSessionsChanged,
  paused = false,
}: {
  session: SessionSummary | null;
  brains: Brain[];
  onSessionsChanged: () => void;
  paused?: boolean; // 查看子页面/主页时：保留头部+历史，输入区换成只读提示（功能后续开放）
}) {
  const { t } = useI18n();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [live, setLive] = useState<Turn | null>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  // 点了停止之后、这一轮真的收尾之前：世界那边正在做的那一步还得做完，所以有个中间态。
  const [stopping, setStopping] = useState(false);
  // 思考区的总开关。auto=正在跑的那轮展开、历史折叠（老行为）；all/none=用户一键全展开/全折叠。
  // 思考区展开策略。默认 auto = 实时回合展开、历史回合折叠。
  // ?expand=all / ?expand=none 可从地址栏指定初值——分享链接时能直接把思考摊开给人看,
  // 出文档截图时也用它(headless 截图点不了鼠标)。
  const [expand, setExpand] = useState<"auto" | "all" | "none">(() => {
    if (typeof window === "undefined") return "auto";
    const v = new URLSearchParams(window.location.search).get("expand");
    return v === "all" || v === "none" ? v : "auto";
  });
  const bottomRef = useRef<HTMLDivElement>(null);
  const openFor = (isLive: boolean) => (expand === "all" ? true : expand === "none" ? false : isLive);

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
        else if (e.type === "progress")
          // 长动作进度：追加到当前工具步的结果区（实时看到"已夹取，正在移向 e4"，不黑等）
          upd((t) => {
            if (!t.thinking.length) return t;
            const i = t.thinking.length - 1;
            return {
              ...t,
              thinking: t.thinking.map((th, j) =>
                j === i ? { ...th, tool_results: [...th.tool_results, `⏳ ${e.message}`] } : th
              ),
            };
          });
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
      upd((turn) => ({ ...turn, reply: t("(连不上后端)") }));
    } finally {
      await reload(); // 用记录里的完整回合替换 live(此后折叠收起)
      setLive(null);
      setBusy(false);
      setStopping(false);
      onSessionsChanged();
    }
  }

  // 停止这一轮。只是给后端置个叫停旗标——它会把当前这一步做完再礼貌收尾，
  // 已经生成的思考和回复照常留在记录里。⛔ 不掐 fetch：那样只是自己捂住眼睛、后端还在跑。
  async function stop() {
    if (!session || !busy || stopping) return;
    setStopping(true);
    await interruptSession(session.id).catch(() => setStopping(false));
  }

  // 大脑名 → 显示名;切换大脑后,在变化处插一条分隔线("开启会话" / "切换为")
  const brainLabel = (n?: string) => brains.find((b) => b.name === n)?.label ?? n ?? "";
  let _lastBrain: string | undefined;
  // ⚠️ 回调参数不能叫 t——会把翻译函数 t() 遮蔽掉（第一版就这么写的，当场报错）
  const seps = turns.map((turn) => {
    if (turn.brain && turn.brain !== _lastBrain) {
      const txt = _lastBrain === undefined
        ? t("使用 {brain} 开启会话", { brain: brainLabel(turn.brain) })
        : t("切换为 {brain}", { brain: brainLabel(turn.brain) });
      _lastBrain = turn.brain;
      return txt;
    }
    return null;
  });

  return (
    <aside className="flex h-screen flex-col border-l border-neutral-800 bg-neutral-900">
      <header className="border-b border-neutral-800 p-3">
        <div className="mb-2 flex items-center justify-between text-xs">
          <span className="font-medium text-neutral-200">{t("和 ANIMA 对话")}</span>
          <span className="flex items-center gap-2">
            {/* 长回合的思考很长——给一个总开关，一下把全部回合的思考区收起或摊开 */}
            {(turns.length > 0 || live) && (
              <button
                onClick={() => setExpand(expand === "all" ? "none" : "all")}
                title={t("一键展开 / 折叠所有回合的思考过程")}
                className="rounded border border-neutral-700 px-1.5 py-0.5 text-[10px] text-neutral-400 hover:border-neutral-500"
              >
                {expand === "all" ? t("折叠思考") : t("展开思考")}
              </button>
            )}
            <span className="text-neutral-400">🌐 {session?.world ?? (session ? t("纯聊天") : t("无会话"))}</span>
          </span>
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
            {t("当前大脑")}:{curBrain.vendor} · {curBrain.label}（{curBrain.model}）
          </div>
        )}
      </header>

      <Notebook session={session} />

      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {!session && !paused && (
          <div className="p-4 text-center text-xs text-neutral-500">{t("请在左边新建或选择一个会话")}</div>
        )}
        {turns.map((t, i) => (
          <Fragment key={i}>
            {seps[i] && <Divider text={seps[i]!} />}
            <TurnView turn={t} open={openFor(false)} />
          </Fragment>
        ))}
        {live && <TurnView turn={live} open={openFor(true)} live />}
        {busy && !live?.reply && (
          <div className="text-xs text-neutral-500">
            {stopping ? t("正在收尾——当前这一步做完就停…") : t("ANIMA 思考中…")}
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {paused ? (
        <div className="border-t border-neutral-800 p-4 text-center text-xs text-neutral-500">
          {t("查看子页面中 · 对话暂不可用（后续开放）")}
        </div>
      ) : (
        session &&
        (frozen ? (
          <div className="border-t border-neutral-800 p-4 text-center text-xs text-neutral-500">
            {t("🔒 这个会话已冻结、只读。新建会话可继续。")}
            <span className="group relative ml-1 cursor-help text-neutral-400">
              ❓
              <span
                className="pointer-events-none invisible absolute bottom-full left-1/2 z-10 mb-1 w-64 -translate-x-1/2
                           rounded-lg bg-neutral-800 p-2 text-left text-[11px] leading-relaxed text-neutral-300
                           opacity-0 shadow-lg transition-opacity group-hover:visible group-hover:opacity-100"
              >
                {t("为保护物理设备的安全:同一个世界一旦开了新会话,原来的会话会立刻被锁定、变成只读——你仍可以翻看它的历史轨迹,但它不再接入实时感知系统,也不能再向世界下达动作。")}
              </span>
            </span>
          </div>
        ) : (
          <div className="flex gap-2 border-t border-neutral-800 p-3">
            {/* 生成期间输入框照样能打字(先把下一句写好)，只是回车不发送——send() 里 busy 直接返回 */}
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send()}
              placeholder={busy ? t("这一轮跑完再发下一句…") : t("给 ANIMA 下达一个指令…")}
              className="flex-1 rounded-xl bg-neutral-800 px-3 py-2 text-sm outline-none placeholder:text-neutral-500"
            />
            {/* 同一个位置两种状态：闲着=发送，跑着=停止。长回合里这是用户唯一的刹车。 */}
            {busy ? (
              <button
                onClick={stop}
                disabled={stopping}
                title={t("停止这一轮（当前这一步做完就停，说「继续」可接着来）")}
                className="flex items-center gap-1.5 rounded-xl bg-neutral-700 px-4 py-2 text-sm font-medium disabled:opacity-60"
              >
                <StopIcon />
                {stopping ? t("停止中…") : t("停止")}
              </button>
            ) : (
              <button onClick={send} className="rounded-xl bg-blue-600 px-4 py-2 text-sm font-medium">
                {t("发送")}
              </button>
            )}
          </div>
        )))}
    </aside>
  );
}
