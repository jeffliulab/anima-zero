"use client";
import { useEffect, useRef, useState } from "react";

import { useI18n } from "@/lib/i18n";
import {
  getSessionLogs,
  listSessions,
  POLL_SESSION_LOGS_MS,
  type SessionLogEntry,
  type SessionSummary,
} from "@/lib/api";

// 三类流水的标签与色点（色点区分类别，文字保持中性色、深浅主题都可读）：
// LLM=大脑↔大模型；世界=大脑↔世界(MCP)；服务=大脑↔挂载服务(顾问，如引擎)。
// ⛔ 返回的是**英文原文**（= 词条 key），显示的地方再过一次 t()——这个函数是模块级的，
//    调不了 hook，所以翻译发生在渲染处，而不是在这里。
function kindTag(kind: string): { tag: string; dot: string } {
  if (kind === "llm_call") return { tag: "LLM", dot: "bg-purple-400" };
  if (kind === "world_call") return { tag: "World", dot: "bg-sky-400" };
  if (kind === "service_call") return { tag: "Service", dot: "bg-emerald-400" };
  return { tag: kind || "Other", dot: "bg-neutral-500" };
}

// 把一条流水拍平成"带每一个信息要素"的可读文本（一键复制用）——存了什么字段就带什么。
//
// ⛔ 这一份**有意保持英文正典、不跟界面语言走**。它不是界面，是**要被复制出去**的诊断文本：
//    贴进 issue、发给别人看、和后端日志对照。那种场合下"跟着我的界面语言变"是负担而不是便利。
//    界面上看到的同样内容照常翻译（见下面 JSX 里的 t(...)），复制出去的这份保持一种语言。
function fmtEntry(e: SessionLogEntry): string {
  const head = `#${e.id}  ${e.ts}  [${kindTag(e.kind).tag}]`;
  const sess = `session: ${e.session || "(none)"}`;
  if (e.kind === "llm_call") {
    const tok = e.tokens
      ? `in ${e.tokens.input} / out ${e.tokens.output} / total ${e.tokens.total}`
      : "(none)";
    return [
      `${head}  ${e.model}`,
      sess,
      `context ${e.n_history} · tools ${e.n_tools} · ${e.has_image ? "with image" : "no image"} · ${e.ms}ms`,
      `tokens: ${tok}`,
      `user: ${e.last_user || "(none)"}`,
      `reply: ${e.reply || "(none)"}`,
      `tool calls: ${e.tool_calls.length ? e.tool_calls.join(", ") : "(none)"}`,
      e.error ? `error: ${e.error}` : "",
      `system prompt:\n${e.system}`,
    ]
      .filter(Boolean)
      .join("\n");
  }
  const peer = e.kind === "world_call" ? e.world : e.server;
  return [
    `${head}  ${peer} · ${e.method} · ${e.ms}ms`,
    sess,
    `sent: ${e.summary}`,
    `returned: ${JSON.stringify(e.resp)}`,
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
  const { t } = useI18n();
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
          <span className="text-neutral-500">Session Logs · {t("Session: ")}</span>
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
                {t("deleted")} {id.slice(0, 12)}…
              </option>
            ))}
            <option value={ALL}>{t("All (every session merged)")}</option>
          </select>
          <span className="text-[11px] text-neutral-500">
            {selected === ALL
              ? `${entries.length} ${t("entries")}`
              : (cur ? (cur.world ?? t("Chat only")) + " · " + cur.brain + " · " : "") + `${entries.length} ${t("entries")}`}
          </span>
          <button
            onClick={copyAll}
            disabled={entries.length === 0}
            title={t("Copy every listed log entry (all fields) to the clipboard")}
            className="ml-auto rounded-md border border-neutral-700 bg-neutral-800 px-2 py-1 text-[11px] text-neutral-200 hover:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {copied ? t("Copied ✓") : t("Copy all logs")}
          </button>
        </div>
        <div className="flex items-baseline gap-2">
          <h1 className="truncate text-sm font-semibold">
            {selected === ALL ? t("All activity (every session merged)") : cur ? cur.title : selected ? `${t("Session: ")}${selected.slice(0, 12)}…` : t("(no session selected)")}
          </h1>
        </div>
        <p className="mt-1 text-[11px] leading-relaxed text-neutral-500">
          {t("Everything this session did, merged by time:")}
          <span className="mx-1 inline-block h-2 w-2 rounded-full bg-purple-400" />{t("LLM calls (thinking)")}·
          <span className="mx-1 inline-block h-2 w-2 rounded-full bg-sky-400" />{t("world round-trips (see / act, MCP)")}·
          <span className="mx-1 inline-block h-2 w-2 rounded-full bg-emerald-400" />{t("service calls (asking an advisor, e.g. the engine)")}
          {t("— one chain showing what ANIMA saw, thought, and called.")}
        </p>
      </div>

      {/* 日志流：只有这块滚动 */}
      <div ref={termRef} className="min-h-0 flex-1 overflow-y-auto bg-neutral-950 p-3">
        {entries.length === 0 ? (
          <div className="text-xs text-neutral-600">
            {selected === ALL
              ? t("(No traffic yet. Send a message on the main screen and the whole chain shows up here.)")
              : t("(This session has no traffic yet.)")}
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
                    <span className="font-medium text-neutral-300">{t(src.tag)}</span>
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
                    <summary className="cursor-pointer text-[10px] text-neutral-600">{t("returned")}</summary>
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
                    {t("context")} {e.n_history} · {t("tools")} {e.n_tools}{e.has_image ? ` · ${t("with image")}` : ""} · {e.ms}ms
                  </span>
                  {e.error && <span className="w-full text-rose-500">✗ {e.error}</span>}
                </div>
                {e.last_user && (
                  <div className="mt-1.5 whitespace-pre-wrap text-xs leading-relaxed">
                    <span className="text-neutral-500">{t("user:")}</span>
                    <span className="text-neutral-300">{e.last_user}</span>
                  </div>
                )}
                {e.reply && (
                  <div className="mt-1 whitespace-pre-wrap text-xs leading-relaxed">
                    <span className="text-neutral-500">{t("reply:")}</span>
                    <span className="text-neutral-100">{e.reply}</span>
                  </div>
                )}
                {e.tool_calls.length > 0 && (
                  <div className="mt-1 text-xs leading-relaxed">
                    <span className="text-neutral-500">{t("tool calls:")}</span>
                    <span className="font-mono text-neutral-200">{e.tool_calls.join(", ")}</span>
                  </div>
                )}
                {e.tokens && (
                  <div className="mt-1 text-[11px] text-neutral-500">
                    tokens: {t("in")} {e.tokens.input} · {t("out")} {e.tokens.output} · {t("total")} {e.tokens.total}
                  </div>
                )}
                <details className="mt-1.5">
                  <summary className="cursor-pointer text-[10px] text-neutral-500">{t("system prompt (full)")}</summary>
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
