"use client";
import { useEffect, useRef, useState } from "react";
import {
  getAnimaLogs,
  listSessions,
  POLL_ANIMA_LOGS_MS,
  type AnimaLogEntry,
  type SessionSummary,
} from "@/lib/api";

// 据系统提示前缀粗分"这次调用是干嘛的"——纯展示用，便于 debug 时一眼区分主循环/意图/解说/陪聊。
function source(system: string): { tag: string; color: string } {
  const s = system || "";
  if (s.includes("意图分类器") || s.includes("意图判断")) return { tag: "意图分类", color: "text-amber-300" };
  if (s.includes("对弈伙伴")) return { tag: "对弈陪聊", color: "text-sky-300" };
  if (s.includes("对弈陪伴") || s.includes("解说")) return { tag: "解说", color: "text-emerald-300" };
  if (s.includes("ANIMA")) return { tag: "主循环", color: "text-purple-300" };
  return { tag: "其它", color: "text-neutral-400" };
}

const ALL = ""; // 选中值为空串=看全部（合并所有会话）

export default function AnimaLogs() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]); // 会话列表（与主界面同源、同序：created_at 倒序）
  const [logged, setLogged] = useState<Set<string>>(new Set()); // 哪些会话有日志（打个标）
  const [selected, setSelected] = useState<string>(ALL); // 当前选中的会话 id；ALL=全部
  const [entries, setEntries] = useState<AnimaLogEntry[]>([]);
  const termRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const load = async () => {
      const [ss, logs] = await Promise.all([
        listSessions().catch(() => [] as SessionSummary[]),
        getAnimaLogs(500, selected).catch(() => ({ entries: [], sessions: [] as string[] })),
      ]);
      setSessions(ss);
      setLogged(new Set(logs.sessions)); // 后端无论是否过滤都回完整的 sessions 列表
      setEntries(logs.entries);
    };
    load();
    const id = setInterval(load, POLL_ANIMA_LOGS_MS);
    return () => clearInterval(id);
  }, [selected]);

  useEffect(() => {
    termRef.current?.scrollTo(0, termRef.current.scrollHeight);
  }, [entries]);

  const cur = sessions.find((s) => s.id === selected);
  // 有日志、但已不在会话列表里的（如已删除的会话）——也列出来，免得日志查不到
  const orphanLogged = [...logged].filter((id) => !sessions.some((s) => s.id === id));

  return (
    <main className="flex h-screen bg-neutral-950 text-neutral-200">
      {/* 左侧边栏：会话列表（点一个看它的 logs） */}
      <aside className="flex w-72 shrink-0 flex-col border-r border-neutral-800 bg-neutral-900">
        <div className="border-b border-neutral-800 p-3">
          <div className="text-sm font-semibold">anima-logs</div>
          <div className="mt-0.5 text-[11px] text-neutral-500">脑 ↔ 大模型 · 按会话查</div>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {/* 全部 */}
          <button
            onClick={() => setSelected(ALL)}
            className={`mb-1 w-full rounded-lg p-2 text-left text-xs ${
              selected === ALL ? "bg-neutral-800" : "hover:bg-neutral-800/50"
            }`}
          >
            <span className="font-medium">全部</span>
            <span className="ml-1 text-[10px] text-neutral-500">（合并所有会话）</span>
          </button>

          {sessions.map((s) => (
            <button
              key={s.id}
              onClick={() => setSelected(s.id)}
              className={`mb-1 block w-full rounded-lg p-2 text-left text-xs ${
                s.id === selected ? "bg-neutral-800" : "hover:bg-neutral-800/50"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="truncate font-medium">{s.title}</span>
                {logged.has(s.id) ? (
                  <span className="ml-1 shrink-0 text-[10px] text-emerald-400" title="有 LLM 调用日志">●</span>
                ) : (
                  <span className="ml-1 shrink-0 text-[10px] text-neutral-700" title="还没有日志">○</span>
                )}
              </div>
              <div className="mt-0.5 text-[10px] text-neutral-500">
                {(s.world ?? "纯聊天") + " · " + s.brain}
              </div>
            </button>
          ))}

          {orphanLogged.length > 0 && (
            <div className="mt-2 border-t border-neutral-800 pt-2">
              <div className="px-2 pb-1 text-[10px] text-neutral-600">已删除会话（仍有日志）</div>
              {orphanLogged.map((id) => (
                <button
                  key={id}
                  onClick={() => setSelected(id)}
                  className={`mb-1 block w-full rounded-lg p-2 text-left text-xs ${
                    id === selected ? "bg-neutral-800" : "hover:bg-neutral-800/50"
                  }`}
                >
                  <span className="font-mono text-neutral-400">{id.slice(0, 12)}…</span>
                  <span className="ml-1 text-[10px] text-emerald-400">●</span>
                </button>
              ))}
            </div>
          )}

          {sessions.length === 0 && orphanLogged.length === 0 && (
            <div className="p-3 text-[11px] text-neutral-600">还没有会话。去主界面发条消息、或开一盘棋。</div>
          )}
        </div>
        <div className="flex items-center gap-3 border-t border-neutral-800 p-3 text-xs">
          <a href="/awi" className="text-blue-400 hover:underline">AWI →</a>
          <a href="/" className="text-blue-400 hover:underline">← 回主界面</a>
        </div>
      </aside>

      {/* 右侧：选中会话的详细 logs */}
      <section className="flex min-w-0 flex-1 flex-col">
        <div className="border-b border-neutral-800 p-3">
          <div className="flex items-baseline justify-between">
            <h1 className="text-sm font-semibold">
              {selected === ALL ? "全部 LLM 调用（合并所有会话）" : cur ? cur.title : `会话 ${selected.slice(0, 12)}…`}
            </h1>
            <span className="text-[11px] text-neutral-500">
              {selected === ALL
                ? `${entries.length} 条`
                : (cur ? (cur.world ?? "纯聊天") + " · " + cur.brain + " · " : "") + `${entries.length} 条`}
            </span>
          </div>
          <p className="mt-1 text-[11px] leading-relaxed text-neutral-500">
            ANIMA ↔ 大模型 的详细思考流量（与 <code className="rounded bg-neutral-800 px-1">/awi</code> 看的"脑↔世界"互补）。
            一个会话一个文件 <code className="rounded bg-neutral-800 px-1">logs/anima/session-&lt;id&gt;.jsonl</code>；
            主循环 / 意图分类 / 解说 / 对弈陪聊每一次调用都在这里。
            <span className="text-neutral-600">（token 用量暂缺，待各 provider 补。）</span>
          </p>
        </div>

        <div ref={termRef} className="flex-1 overflow-y-auto bg-black p-3 font-mono text-xs leading-relaxed">
          {entries.length === 0 ? (
            <div className="text-neutral-600">
              {selected === ALL
                ? "(暂无流量；去主界面发条消息、或开一盘棋，这里就会出现每一次 LLM 调用)"
                : "(这个会话还没有 LLM 调用)"}
            </div>
          ) : (
            entries.map((e) => {
              const src = source(e.system);
              return (
                <div key={e.id} className="mb-2 border-b border-neutral-900 pb-1.5">
                  <div>
                    <span className="text-neutral-600">[{e.ts}]</span>{" "}
                    <span className={src.color}>{src.tag}</span>{" "}
                    {selected === ALL && e.session && (
                      <span className="text-neutral-600">·{e.session.slice(0, 8)}</span>
                    )}{" "}
                    <span className="text-neutral-500">{e.model}</span>{" "}
                    <span className="text-neutral-600">
                      ·{e.n_history}史/{e.n_tools}工具{e.has_image ? "/带图" : ""} ({e.ms}ms)
                    </span>
                    {e.error && <span className="text-rose-400"> · ✗ {e.error}</span>}
                  </div>
                  {e.last_user && <div className="text-neutral-400">用户：{e.last_user}</div>}
                  {e.reply && <div className="text-amber-200">回复：{e.reply}</div>}
                  {e.tool_calls.length > 0 && (
                    <div className="text-green-300">工具调用：{e.tool_calls.join(", ")}</div>
                  )}
                  <details className="mt-0.5">
                    <summary className="cursor-pointer text-[10px] text-neutral-500">system 提示前缀</summary>
                    <pre className="overflow-x-auto whitespace-pre-wrap text-[10px] text-neutral-500">{e.system}</pre>
                  </details>
                </div>
              );
            })
          )}
        </div>
      </section>
    </main>
  );
}
