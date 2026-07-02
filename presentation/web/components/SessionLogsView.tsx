"use client";
import { useEffect, useRef, useState } from "react";
import {
  getSessionLogs,
  listSessions,
  POLL_SESSION_LOGS_MS,
  type SessionLogEntry,
  type SessionSummary,
} from "@/lib/api";

// 三类流水的标签与色点（色点区分类别，文字保持中性色、深浅主题都可读）：
// LLM=大脑↔大模型；世界=大脑↔世界(MCP)；服务=大脑↔挂载服务(顾问，如引擎)。
function kindTag(kind: string): { tag: string; dot: string } {
  if (kind === "llm_call") return { tag: "LLM", dot: "bg-purple-400" };
  if (kind === "world_call") return { tag: "世界", dot: "bg-sky-400" };
  if (kind === "service_call") return { tag: "服务", dot: "bg-emerald-400" };
  return { tag: kind || "其它", dot: "bg-neutral-500" };
}

// 把一条流水拍平成"带每一个信息要素"的可读文本（一键复制用）——存了什么字段就带什么。
function fmtEntry(e: SessionLogEntry): string {
  const head = `#${e.id}  ${e.ts}  [${kindTag(e.kind).tag}]`;
  const sess = `会话：${e.session || "（无会话）"}`;
  if (e.kind === "llm_call") {
    const tok = e.tokens
      ? `输入 ${e.tokens.input} / 输出 ${e.tokens.output} / 合计 ${e.tokens.total}`
      : "（无）";
    return [
      `${head}  ${e.model}`,
      sess,
      `上下文 ${e.n_history} 条 · 可用工具 ${e.n_tools} 个 · ${e.has_image ? "含截图" : "无截图"} · 耗时 ${e.ms}ms`,
      `tokens：${tok}`,
      `用户：${e.last_user || "（无）"}`,
      `回复：${e.reply || "（无）"}`,
      `工具调用：${e.tool_calls.length ? e.tool_calls.join(", ") : "（无）"}`,
      e.error ? `错误：${e.error}` : "",
      `system 提示：\n${e.system}`,
    ]
      .filter(Boolean)
      .join("\n");
  }
  const peer = e.kind === "world_call" ? e.world : e.server;
  return [
    `${head}  ${peer} · ${e.method} · ${e.ms}ms`,
    sess,
    `发出：${e.summary}`,
    `返回：${JSON.stringify(e.resp)}`,
  ].join("\n");
}

const ALL = ""; // 选中值为空串=看全部（合并所有会话）

// Session Logs：本会话全部行为流水（LLM 调用 / MCP 世界往返 / 服务调用，按时间合并）。
// 会话下拉与一键复制沿自 anima-logs（逐行保留）；默认选【当前会话】，没日志就退到第一个有日志的。
// embedded=true：内嵌主页中间区（h-full）；false：/session-logs 整页独立版（h-screen）。
export default function SessionLogsView({
  embedded = false,
  sessionId = "",
}: {
  embedded?: boolean;
  sessionId?: string;
}) {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [logged, setLogged] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<string>(sessionId || ALL);
  const [entries, setEntries] = useState<SessionLogEntry[]>([]);
  const termRef = useRef<HTMLDivElement>(null);
  const resolvedRef = useRef(false); // 默认会话只自动定一次，之后听用户的下拉
  const [copied, setCopied] = useState(false);

  // 一键复制当前所列的全部日志（带每个信息要素）。clipboard 不可用时静默不崩。
  const copyAll = async () => {
    if (entries.length === 0) return;
    const text = entries.map(fmtEntry).join("\n\n" + "─".repeat(40) + "\n\n");
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* 非 https / 旧浏览器无 clipboard 权限：不崩，忽略 */
    }
  };

  useEffect(() => {
    const load = async () => {
      const [ss, logs] = await Promise.all([
        listSessions().catch(() => [] as SessionSummary[]),
        getSessionLogs(500, selected).catch(() => ({ entries: [], sessions: [] as string[] })),
      ]);
      setSessions(ss);
      setLogged(new Set(logs.sessions));
      setEntries(logs.entries);
    };
    load();
    const id = setInterval(load, POLL_SESSION_LOGS_MS);
    return () => clearInterval(id);
  }, [selected]);

  // 拿到会话/日志清单后，定一次默认选中（仅一次；之后用户下拉说了算）
  useEffect(() => {
    if (resolvedRef.current) return;
    if (sessions.length === 0 && logged.size === 0) return; // 还没数据，等下一轮
    resolvedRef.current = true;
    const has = (id: string) => logged.has(id);
    const def =
      sessionId && has(sessionId)
        ? sessionId
        : sessions.find((s) => has(s.id))?.id ?? [...logged][0] ?? sessionId ?? ALL;
    if (def !== selected) setSelected(def);
  }, [sessions, logged, sessionId, selected]);

  useEffect(() => {
    termRef.current?.scrollTo(0, termRef.current.scrollHeight);
  }, [entries]);

  const cur = sessions.find((s) => s.id === selected);
  const orphanLogged = [...logged].filter((id) => !sessions.some((s) => s.id === id));

  return (
    <main className={`flex min-h-0 min-w-0 flex-col ${embedded ? "h-full" : "h-screen"} bg-neutral-950 text-neutral-200`}>
      {/* 顶部：会话下拉 + 标题/计数（固定，不随日志滚动） */}
      <div className="shrink-0 border-b border-neutral-800 p-3">
        <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
          <span className="text-neutral-500">Session Logs · 会话：</span>
          <select
            value={selected}
            onChange={(e) => {
              resolvedRef.current = true;
              setSelected(e.target.value);
            }}
            className="rounded-md border border-neutral-700 bg-neutral-800 px-2 py-1 text-xs text-neutral-200"
          >
            {sessions.map((s) => (
              <option key={s.id} value={s.id}>
                {s.title}
              </option>
            ))}
            {orphanLogged.map((id) => (
              <option key={id} value={id}>
                已删除 {id.slice(0, 12)}…
              </option>
            ))}
            <option value={ALL}>全部（合并所有会话）</option>
          </select>
          <span className="text-[11px] text-neutral-500">
            {selected === ALL
              ? `${entries.length} 条`
              : (cur ? (cur.world ?? "纯聊天") + " · " + cur.brain + " · " : "") + `${entries.length} 条`}
          </span>
          <button
            onClick={copyAll}
            disabled={entries.length === 0}
            title="把当前所列的全部日志（含每个信息要素）复制到剪贴板"
            className="ml-auto rounded-md border border-neutral-700 bg-neutral-800 px-2 py-1 text-[11px] text-neutral-200 hover:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {copied ? "已复制 ✓" : "复制全部日志"}
          </button>
        </div>
        <div className="flex items-baseline gap-2">
          <h1 className="truncate text-sm font-semibold">
            {selected === ALL ? "全部行为流水（合并所有会话）" : cur ? cur.title : selected ? `会话 ${selected.slice(0, 12)}…` : "（未选会话）"}
          </h1>
        </div>
        <p className="mt-1 text-[11px] leading-relaxed text-neutral-500">
          本会话的全部行为流水，按时间合并：
          <span className="mx-1 inline-block h-2 w-2 rounded-full bg-purple-400" />LLM 调用（想）·
          <span className="mx-1 inline-block h-2 w-2 rounded-full bg-sky-400" />世界往返（看/动，MCP）·
          <span className="mx-1 inline-block h-2 w-2 rounded-full bg-emerald-400" />服务调用（问顾问，如引擎）
          ——「ANIMA 看到什么、想了什么、调了什么」一条链看全。
        </p>
      </div>

      {/* 日志流：只有这块滚动 */}
      <div ref={termRef} className="min-h-0 flex-1 overflow-y-auto bg-neutral-950 p-3">
        {entries.length === 0 ? (
          <div className="text-xs text-neutral-600">
            {selected === ALL
              ? "(暂无流水；去主界面发条消息，这里就会出现完整的行为链)"
              : "(这个会话还没有流水)"}
          </div>
        ) : (
          entries.map((e) => {
            const src = kindTag(e.kind);
            if (e.kind !== "llm_call") {
              // 世界 / 服务往返：单行紧凑条（summary 直给；返回体折叠）
              const peer = e.kind === "world_call" ? e.world : e.server;
              return (
                <div key={`${e.kind}-${e.id}-${e.t ?? e.ts}`} className="mb-1.5 rounded-md border border-neutral-800/70 bg-neutral-900/30 px-2.5 py-1.5">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px]">
                    <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${src.dot}`} />
                    <span className="font-medium text-neutral-300">{src.tag}</span>
                    <span className="text-neutral-600">#{e.id}</span>
                    <span className="text-neutral-500">{e.ts}</span>
                    <span className="text-neutral-400">{peer}</span>
                    <span className="font-mono text-neutral-300">{e.summary}</span>
                    {selected === ALL && e.session && (
                      <span className="text-neutral-600">·{e.session.slice(0, 8)}</span>
                    )}
                    <span className="ml-auto text-neutral-600">{e.ms}ms</span>
                  </div>
                  <details className="mt-0.5">
                    <summary className="cursor-pointer text-[10px] text-neutral-600">返回</summary>
                    <pre className="mt-1 overflow-x-auto whitespace-pre-wrap rounded border border-neutral-800 bg-neutral-950 p-2 font-mono text-[10px] leading-relaxed text-neutral-500">
                      {JSON.stringify(e.resp, null, 2)}
                    </pre>
                  </details>
                </div>
              );
            }
            return (
              <div key={`${e.kind}-${e.id}-${e.t ?? e.ts}`} className="mb-2 rounded-lg border border-neutral-800 bg-neutral-900/50 p-2.5">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px]">
                  <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${src.dot}`} />
                  <span className="font-medium text-neutral-300">{src.tag}</span>
                  <span className="text-neutral-600">#{e.id}</span>
                  <span className="text-neutral-500">{e.ts}</span>
                  <span className="text-neutral-400">{e.model}</span>
                  {selected === ALL && e.session && (
                    <span className="text-neutral-600">·{e.session.slice(0, 8)}</span>
                  )}
                  <span className="ml-auto text-neutral-600">
                    上下文 {e.n_history} 条 · 可用工具 {e.n_tools} 个{e.has_image ? " · 含截图" : ""} · 耗时 {e.ms}ms
                  </span>
                  {e.error && <span className="w-full text-rose-500">✗ {e.error}</span>}
                </div>
                {e.last_user && (
                  <div className="mt-1.5 whitespace-pre-wrap text-xs leading-relaxed">
                    <span className="text-neutral-500">用户：</span>
                    <span className="text-neutral-300">{e.last_user}</span>
                  </div>
                )}
                {e.reply && (
                  <div className="mt-1 whitespace-pre-wrap text-xs leading-relaxed">
                    <span className="text-neutral-500">回复：</span>
                    <span className="text-neutral-100">{e.reply}</span>
                  </div>
                )}
                {e.tool_calls.length > 0 && (
                  <div className="mt-1 text-xs leading-relaxed">
                    <span className="text-neutral-500">工具调用：</span>
                    <span className="font-mono text-neutral-200">{e.tool_calls.join(", ")}</span>
                  </div>
                )}
                {e.tokens && (
                  <div className="mt-1 text-[11px] text-neutral-500">
                    tokens：输入 {e.tokens.input} · 输出 {e.tokens.output} · 合计 {e.tokens.total}
                  </div>
                )}
                <details className="mt-1.5">
                  <summary className="cursor-pointer text-[10px] text-neutral-500">system 提示（完整）</summary>
                  <pre className="mt-1 overflow-x-auto whitespace-pre-wrap rounded border border-neutral-800 bg-neutral-950 p-2 font-mono text-[10px] leading-relaxed text-neutral-500">
                    {e.system}
                  </pre>
                </details>
              </div>
            );
          })
        )}
      </div>
    </main>
  );
}
