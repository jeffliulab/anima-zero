"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { getGame, stopGame, sayGame, POLL_GAME_EVENTS_MS, type GameEvent, type GameStatus } from "@/lib/api";

// Chess Mode 面板：进入对弈行为树时，【整块右栏】换成它（普通聊天框隐藏），把对弈过程和普通聊天明显分开。
// 它自带输入框：对局中你打的字走 /say 发进对弈循环（认输/不下了→停；否则 ANIMA 回一句）——不再走普通聊天。
// 内部仍叫"行为树"；"Chess Mode / 下棋模式"只是给用户看的名字。布局做成整列 flex：事件流占满中间可滚动，
// 输入框钉在底部，整页不溢出。
export default function ChessModePanel({
  sessionId,
  streamUrl,
  onExit,
}: {
  sessionId: string;
  streamUrl: string | null;
  onExit: () => void;
}) {
  const [status, setStatus] = useState<GameStatus | null>(null);
  const [events, setEvents] = useState<GameEvent[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const sinceRef = useRef(0);
  const pollingRef = useRef(false); // 防并发重入：上一次 poll 没回来就不再发起，避免同一批事件被取两遍
  const feedRef = useRef<HTMLDivElement>(null);

  const poll = useCallback(async () => {
    if (pollingRef.current) return; // 立即 poll + 定时 poll + 严格模式双调 会并发，重入直接跳过
    pollingRef.current = true;
    const g = await getGame(sessionId, sinceRef.current).catch(() => null);
    pollingRef.current = false;
    if (!g) return;
    if (g.status) setStatus(g.status);
    if (g.events && g.events.length) {
      // 按 id 去重再追加（并发/重发兜底）：见过的 id 不再进列表，杜绝 React 重复 key
      setEvents((prev) => {
        const seen = new Set(prev.map((e) => e.id));
        const fresh = g.events!.filter((e) => !seen.has(e.id));
        if (!fresh.length) return prev;
        const maxId = fresh.reduce((m, e) => (e.id > m ? e.id : m), sinceRef.current);
        sinceRef.current = maxId; // since 推进到合并后的最大 id，下次只拿更新的
        return [...prev, ...fresh];
      });
    }
  }, [sessionId]);

  useEffect(() => {
    setEvents([]);
    sinceRef.current = 0;
    poll();
    const t = setInterval(poll, POLL_GAME_EVENTS_MS);
    return () => clearInterval(t);
  }, [poll]);

  useEffect(() => {
    feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight });
  }, [events]);

  const finished = status?.finished;

  async function send() {
    const text = input.trim();
    if (!text || sending || finished) return;
    setSending(true);
    setInput("");
    await sayGame(sessionId, text).catch(() => {}); // 用户的话与 ANIMA 的回应由后端 emit 成事件，下次 poll 显示
    setSending(false);
    poll();
  }

  const color = (k: string) =>
    k === "anima"
      ? "text-amber-200"
      : k === "user"
        ? "text-neutral-100"
        : k === "opponent"
          ? "text-sky-300"
          : k === "end"
            ? "text-emerald-300"
            : k === "fail" || k === "error" || k === "stuck"
              ? "text-rose-300"
              : "text-neutral-400";

  return (
    <div className="flex h-screen flex-col border-l-2 border-amber-500/60 bg-amber-950/20">
      {/* 标签条：明显区别于普通聊天 */}
      <div className="flex items-center justify-between bg-amber-500/20 px-3 py-2">
        <div className="text-sm font-semibold text-amber-200">
          ♟ {status?.display_name ?? "Chess Mode · 下棋模式"}
          <span className="ml-2 text-xs font-normal text-amber-300/80">
            {finished ? "· 已结束" : status?.paused ? "· ⏸ 已暂停" : "· 对弈进行中"}
          </span>
        </div>
        <button
          onClick={async () => {
            await stopGame(sessionId).catch(() => {});
            onExit();
          }}
          className="rounded-md bg-amber-600/80 px-2.5 py-1 text-xs text-white hover:bg-amber-600"
        >
          退出
        </button>
      </div>

      {/* 棋盘 + 状态（顶部固定） */}
      <div className="flex gap-3 p-3">
        {streamUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={streamUrl}
            alt="chess board"
            className="h-36 w-36 shrink-0 rounded-md border border-amber-700/40 bg-black object-contain"
          />
        ) : null}
        <div className="min-w-0 flex-1 text-xs text-neutral-300">
          <div>
            我执 <b className="text-amber-200">{status?.my_side === "white" ? "白" : "黑"}</b>
            {" · "}轮到 <b>{status?.turn === "white" ? "白" : "黑"}</b>
            {status?.my_turn ? "（我）" : "（对手）"}
            {" · 第 "}
            <b>{status?.move_count ?? 0}</b> 手
          </div>
          <div className="mt-1 text-neutral-400">最近：{status?.last ?? "—"}</div>
          <div className="mt-1 text-[11px] text-neutral-500">
            下面的输入框直接对这盘说话：「不下了 / 认输」会退出；其它会跟 ANIMA 聊。
          </div>
        </div>
      </div>

      {/* HITL：ANIMA 在等人回答时，把问题 + 选项显示出来（点选项填进输入框，回车/发送即作答） */}
      {status?.question && !finished && (
        <div className="mx-3 mb-2 rounded-md border border-amber-500/50 bg-amber-500/10 p-2 text-xs text-amber-100">
          <div className="font-semibold">❓ ANIMA 在等你回答：</div>
          <div className="mt-0.5">{status.question.text}</div>
          {status.question.options && status.question.options.length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-1">
              {status.question.options.map((o) => (
                <button
                  key={o}
                  onClick={() => setInput(o)}
                  className="rounded bg-amber-600/70 px-2 py-0.5 text-[11px] text-white hover:bg-amber-600"
                >
                  {o}
                </button>
              ))}
            </div>
          )}
          <div className="mt-1 text-[10px] text-amber-300/70">在下面输入框回答即可。</div>
        </div>
      )}

      {/* 解说/事件流（占满中间，可滚动） */}
      <div
        ref={feedRef}
        className="mx-3 flex-1 overflow-y-auto rounded-md bg-black/40 p-2 text-[13px] leading-relaxed"
      >
        {events.length === 0 ? (
          <div className="text-neutral-500">对弈即将开始…</div>
        ) : (
          events.map((e) => (
            <div key={e.id} className={color(e.channel)}>
              <span className="mr-1 text-neutral-600">[{e.ts}]</span>
              {e.channel === "anima" ? "ANIMA：" : e.channel === "user" ? "你：" : ""}
              {e.text}
            </div>
          ))
        )}
      </div>

      {/* 下棋区输入框（钉在底部）：发进对弈循环，不走普通聊天 */}
      <div className="flex gap-2 border-t border-amber-700/30 p-3">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.nativeEvent.isComposing) send();
          }}
          disabled={!!finished || sending}
          placeholder={finished ? "对局已结束" : "对这盘说点什么…（认输 / 不下了 = 退出）"}
          className="min-w-0 flex-1 rounded-lg border border-amber-700/40 bg-neutral-900 px-3 py-2 text-sm outline-none placeholder:text-neutral-600 disabled:opacity-50"
        />
        <button
          onClick={send}
          disabled={!!finished || sending || !input.trim()}
          className="rounded-lg bg-amber-600/80 px-3 py-2 text-sm text-white hover:bg-amber-600 disabled:opacity-40"
        >
          发送
        </button>
      </div>
    </div>
  );
}
