"use client";
import { useEffect, useRef, useState } from "react";
import {
  getAnimaLogs,
  listSessions,
  POLL_ANIMA_LOGS_MS,
  type AnimaLogEntry,
  type SessionSummary,
} from "@/lib/api";

// 据系统提示前缀粗分"这次调用是干嘛的"。tag=文字标签；dot=类别色点（用色点而非彩色文字，
// 这样深/浅主题下文字都用中性色、始终可读，类别靠左边的小圆点区分）。
function source(system: string): { tag: string; dot: string } {
  const s = system || "";
  if (s.includes("意图分类器") || s.includes("意图判断")) return { tag: "意图分类", dot: "bg-amber-400" };
  if (s.includes("对弈伙伴")) return { tag: "对弈陪聊", dot: "bg-sky-400" };
  if (s.includes("对弈陪伴") || s.includes("解说")) return { tag: "解说", dot: "bg-emerald-400" };
  if (s.includes("ANIMA")) return { tag: "主循环", dot: "bg-purple-400" };
  return { tag: "其它", dot: "bg-neutral-500" };
}

// 把一条日志拍平成"带每一个信息要素"的可读文本（给一键复制用）——存了什么字段，这里就带什么，
// 不只复制界面摘要。配合后端放宽留存上限，复制出来即"所有信息要素"。
function fmtEntry(e: AnimaLogEntry): string {
  const tok = e.tokens
    ? `输入 ${e.tokens.input} / 输出 ${e.tokens.output} / 合计 ${e.tokens.total}`
    : "（无）";
  const lines = [
    `#${e.id}  ${e.ts}  [${source(e.system).tag}]  ${e.model}`,
    `会话：${e.session || "（无会话）"}`,
    `上下文 ${e.n_history} 条 · 可用工具 ${e.n_tools} 个 · ${e.has_image ? "含截图" : "无截图"} · 耗时 ${e.ms}ms`,
    `tokens：${tok}`,
    `用户：${e.last_user || "（无）"}`,
    `回复：${e.reply || "（无）"}`,
    `工具调用：${e.tool_calls.length ? e.tool_calls.join(", ") : "（无）"}`,
    e.error ? `错误：${e.error}` : "",
    `system 提示：\n${e.system}`,
  ];
  return lines.filter(Boolean).join("\n");
}

const ALL = ""; // 选中值为空串=看全部（合并所有会话）

// anima-logs 内嵌面板（定稿版，原 logs3 设计）：无自带会话栏，顶部一个会话下拉自选。
// 默认选【当前会话】（由 sessionId 传入）；它没日志就退到第一个有日志的会话；都没有才退「全部」。
// embedded=true：内嵌主页中间区（h-full）；false：/anima-logs 整页独立版（h-screen）。
export default function AnimaLogsView({
  embedded = false,
  sessionId = "",
}: {
  embedded?: boolean;
  sessionId?: string;
}) {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [logged, setLogged] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<string>(sessionId || ALL);
  const [entries, setEntries] = useState<AnimaLogEntry[]>([]);
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
        getAnimaLogs(500, selected).catch(() => ({ entries: [], sessions: [] as string[] })),
      ]);
      setSessions(ss);
      setLogged(new Set(logs.sessions));
      setEntries(logs.entries);
    };
    load();
    const id = setInterval(load, POLL_ANIMA_LOGS_MS);
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
          <span className="text-neutral-500">anima-logs · 会话：</span>
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
            {selected === ALL ? "全部 LLM 调用（合并所有会话）" : cur ? cur.title : selected ? `会话 ${selected.slice(0, 12)}…` : "（未选会话）"}
          </h1>
        </div>
        <p className="mt-1 text-[11px] leading-relaxed text-neutral-500">
          ANIMA ↔ 大模型 的详细思考流量（与 <code className="rounded bg-neutral-800 px-1">/awi</code> 看的"脑↔世界"互补）：
          主循环 / 意图分类 / 解说 / 对弈陪聊每一次 LLM 调用都在这里。
        </p>
      </div>

      {/* 日志流：只有这块滚动 */}
      <div ref={termRef} className="min-h-0 flex-1 overflow-y-auto bg-neutral-950 p-3">
        {entries.length === 0 ? (
          <div className="text-xs text-neutral-600">
            {selected === ALL
              ? "(暂无流量；去主界面发条消息、或开一盘棋，这里就会出现每一次 LLM 调用)"
              : "(这个会话还没有 LLM 调用)"}
          </div>
        ) : (
          entries.map((e) => {
            const src = source(e.system);
            return (
              <div key={e.id} className="mb-2 rounded-lg border border-neutral-800 bg-neutral-900/50 p-2.5">
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
