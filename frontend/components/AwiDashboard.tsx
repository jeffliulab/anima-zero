"use client";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { tt, useI18n } from "@/lib/i18n";
import { WorldTrust } from "./WorldTrust";
import {
  getAwi, awiEventsUrl, AWI_LOG_SHOWN, POLL_AWI_MS, setWorldConfig, refreshWorld,
  type AwiOverview, type AwiWorld, type AwiService, type AwiTool, type WorldConfigOption,
} from "@/lib/api";

// 回方向(server→ANIMA)的结构化返回；不同 method 用不同字段
type Resp = {
  n_tools?: number;
  tools?: string[];
  img_bytes?: number;
  state?: Record<string, unknown>;
  ok?: boolean;
  message?: string;
  has_data?: boolean;
};
type Ev = { id: number; ts: string; session?: string; world: string; method: string; summary: string; resp?: Resp; ms: number };

const OVERVIEW_POLL_MS = POLL_AWI_MS; // /api/awi 概览多久刷一次（env 可覆盖）

const METHOD_COLOR: Record<string, string> = {
  capabilities: "text-purple-400",
  perceive: "text-cyan-400",
  invoke: "text-green-400",
};

// ---- 卡片风格：色条分区（沿用既有主题）。原始 JSON 一律折叠，正文只留人话。----
function Json({ value }: { value: unknown }) {
  return (
    <pre className="mt-1 overflow-x-auto rounded-md border border-neutral-800 bg-black/50 p-2 text-[10px] leading-relaxed text-neutral-400">
      {JSON.stringify(value ?? {}, null, 2)}
    </pre>
  );
}

// 一个能力卡片：名字 + 类型徽章 + 描述 + 可折叠原始 schema/内容
function CapCard({ name, kind, desc, schema, accent }: {
  name: string; kind?: string; desc?: string; schema?: unknown; accent: string;
}) {
  const { t } = useI18n();
  return (
    <div className="rounded-md border border-neutral-800 bg-neutral-950/50 p-2">
      <div className="flex items-center gap-2">
        <span className={`font-mono text-[13px] ${accent}`}>{name}</span>
        {kind && <span className="rounded bg-neutral-800 px-1.5 py-0.5 text-[10px] text-neutral-400">{kind}</span>}
      </div>
      {desc && <div className="mt-0.5 text-[12px] text-neutral-400">{desc}</div>}
      {schema !== undefined && (
        <details className="mt-0.5">
          <summary className="cursor-pointer text-[10px] text-neutral-500">{t("schema / content")}</summary>
          <Json value={schema} />
        </details>
      )}
    </div>
  );
}

// 色条分区：一个区域标题 + 左侧色边
function Region({ title, color, sub, children }: {
  title: string; color: string; sub?: string; children: ReactNode;
}) {
  return (
    <div className="border-l-2 pl-3" style={{ borderColor: color }}>
      <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide" style={{ color }}>
        {title} {sub && <span className="font-normal normal-case tracking-normal text-neutral-600">· {sub}</span>}
      </div>
      <div className="space-y-1.5">{children}</div>
    </div>
  );
}

// 把回方向(server→ANIMA)格式化成一句人话；perceive 的回程 state 是审计点：
// state 允许带角色 meta，但红线是【绝不许夹带棋盘真值】(FEN/局面/着法)。疑似含真值才标 ⚠。
function fmtResp(method: string, resp?: Resp): { text: string; warn: boolean } {
  if (!resp) return { text: "(none)", warn: false };
  if (method === "capabilities")
    return { text: `${resp.n_tools ?? 0} ${tt("capabilities")} [${(resp.tools ?? []).join(", ")}]`, warn: false };
  if (method === "perceive") {
    const st = resp.state ?? {};
    const blob = JSON.stringify(st);
    // 启发式：含 fen/board/pieces/legal 或 FEN 样式(行间 '/') → 疑似棋盘真值
    const looksLikeTruth = /fen|"board"|pieces|legal|[pnbrqkPNBRQK1-8]+\/[pnbrqkPNBRQK1-8]+/.test(blob);
    return {
      text: `图片 ${resp.img_bytes ?? 0} 字节 · 回程 state: ${blob}${looksLikeTruth ? tt("(⚠ looks like it leaked ground truth)") : tt("(no ground truth found ✓)")}`,
      warn: looksLikeTruth,
    };
  }
  if (method === "invoke")
    return {
      text: `${resp.ok ? "ok ✓" : "FAIL ✗"} · ${resp.message ?? ""}${resp.has_data ? tt(" · with data") : ""}`,
      warn: false,
    };
  return { text: JSON.stringify(resp), warn: false };
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-neutral-800 bg-neutral-900 p-3">
      <div className="text-2xl font-semibold">{value}</div>
      <div className="text-xs text-neutral-500">{label}</div>
    </div>
  );
}

// 🌍 World Server 卡：ANIMA 栖身的现实——按 MCP 原语分四区：Tools（动作）/ Resources（感知）/
// Prompts（说明书）+ Status（场外信息，anima 看不到：/status 真值、/stream、/health，仅人看）。
function WorldCard({ w }: { w: AwiWorld }) {
  const { t } = useI18n();
  const online = w.online;
  const stateSchema = w.state_schema;
  const guidance = w.guidance ?? "";
  const hasStatus =
    w.status != null && JSON.stringify(w.status) !== "{}" && JSON.stringify(w.status) !== "null";
  return (
    <div className="rounded-xl border border-neutral-800 bg-neutral-900 p-4">
      <div className="flex items-center justify-between">
        <span className="font-medium">
          🌍 {w.name}{" "}
          <span className="text-xs text-neutral-500">{t("World Server · the reality ANIMA inhabits")}{w.version ? ` v${w.version}` : ""}</span>
        </span>
        <div className="flex items-center gap-2">
          <RefreshTools name={w.name} online={online} />
          <span className={`text-xs ${online ? "text-green-400" : "text-red-400"}`}>● {online ? t("online") : t("offline")}</span>
        </div>
      </div>
      <div className="mt-1 text-[11px] text-neutral-500">{w.url}</div>

      {/* 审批闸：世界的工具与说明书在被批准之前不进大脑，所以下面那几区会是空的——
          这块必须紧挨着它们，否则看的人只会以为这个世界坏了。 */}
      <WorldTrust name={w.name} state={w.trust ?? ""} onApproved={() => location.reload()} />

      <div className="mt-3 space-y-3">
        {online && (w.config?.options?.length ?? 0) > 0 && (
          <Region title="Config" color="#a78bfa"
            sub={t("How this world is set up (declared over AWI; ⚠️ you change it — ANIMA is only told the current state and cannot change it)")}>
            {w.config!.options!.map((o) => (
              <ConfigOption key={o.key} world={w.name} opt={o} />
            ))}
          </Region>
        )}
        <Region title="Tools" color="#3fb950" sub={t("Tools ANIMA can call (world-changing ones pass the safety gate)")}>
          {w.tools.map((t) => (
            <CapCard key={t.name} name={t.name} kind={(t as AwiTool).kind} desc={t.description}
              schema={t.parameters} accent="text-green-300" />
          ))}
          {w.tools.length === 0 && (
            <div className="text-xs text-neutral-500">{online ? t("(no actions — observation only)") : t("(offline — unavailable)")}</div>
          )}
        </Region>

        <Region title="Resources" color="#58a6ff" sub={t("What ANIMA perceives: a frame snapshot + structured state")}>
          {!online ? (
            <div className="text-xs text-neutral-500">{t("(offline — cannot fetch)")}</div>
          ) : (
            <CapCard name="anima://observation" kind="读一次给一份" accent="text-sky-300"
              desc={t("What the world shows the brain: a frame snapshot (png) plus structured state (listed below — never ground truth).")}
              schema={stateSchema && Object.keys(stateSchema).length ? stateSchema : (w.state ?? {})} />
          )}
        </Region>

        <Region title="Prompts" color="#f59e0b" sub={t("The world's guidance: how it introduces itself to the brain (read into the system prompt)")}>
          {!online ? (
            <div className="text-xs text-neutral-500">{t("(offline — cannot fetch)")}</div>
          ) : guidance ? (
            <div className="whitespace-pre-wrap rounded-md border border-neutral-800 bg-neutral-950/50 p-2 text-[12px] leading-relaxed text-[var(--text-accent-amber)]">
              {guidance}
            </div>
          ) : (
            <div className="text-xs text-neutral-500">{t("(this world offers no guidance)")}</div>
          )}
        </Region>

        <Region title="Status" color="#f85149" sub={t("Out-of-band world info ANIMA cannot see (for humans only, not over MCP)")}>
          <div className="text-[12px] text-neutral-400">
            {t("🔒 Ground truth for debugging (the human's god view):")}
            {hasStatus ? <Json value={w.status} /> : <span className="text-neutral-500"> {t("(this world has no /status)")}</span>}
          </div>
          <div className="text-[11px] leading-relaxed text-neutral-500">
            {t("Also out of band: \ud83c\udfac /stream video — continuous pictures for people, not the brain\u2019s discrete snapshots \u00b7 \ud83d\udd0c /health liveness — the dot at the top right, about every {sec}s, not counted as traffic.", { sec: OVERVIEW_POLL_MS / 1000 })}
          </div>
        </Region>
      </div>
    </div>
  );
}

// 世界配置的一项：一个下拉 + 一个"改"。⛔ 前端不认识任何具体键名（body/相机/…）——
// 世界声明什么就渲染什么，加新配置项不用改这里一行代码。
// 改完要整页重取：换了配置，世界的工具单/说明书都可能变了（后端已顺手让大脑重新握手）。
function ConfigOption({ world, opt }: { world: string; opt: WorldConfigOption }) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const choices = opt.choices ?? [];
  async function pick(v: string) {
  const { t } = useI18n();
    if (v === opt.value || busy) return;
    setBusy(true);
    setMsg(t("Switching… (the world is being rebuilt, this takes a few seconds)"));
    const r = await setWorldConfig(world, opt.key, v).catch(() => ({ ok: false, message: t("Cannot reach the backend") }));
    setMsg(r.message ?? (r.ok ? t("Switched") : t("Failed")));
    setBusy(false);
  }
  return (
    <div className="rounded-md border border-neutral-800 bg-neutral-950/50 p-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[12px] text-violet-300">{opt.label || opt.key}</span>
        {choices.length ? (
          <select
            value={opt.value}
            disabled={busy}
            onChange={(e) => pick(e.target.value)}
            className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-[12px] text-neutral-200 disabled:opacity-50"
          >
            {choices.map((c) => (
              <option key={c.value} value={c.value}>{c.label || c.value}</option>
            ))}
          </select>
        ) : (
          <span className="font-mono text-[12px] text-neutral-300">{opt.value}</span>
        )}
      </div>
      {opt.description && <div className="mt-1 text-[11px] text-neutral-500">{opt.description}</div>}
      {msg && <div className="mt-1 text-[11px] text-amber-400">{msg}</div>}
    </div>
  );
}

// 「重新握手」：让大脑重新问一遍这个世界有哪些工具。
// 为什么值得一个按钮（v0.9 踩过）：能力清单在首次握手时被缓存，世界那边加了新工具而后端没重启的话，
// 新工具**永远**上不了 LLM 的工具单——上一版新增的环视就这么被藏了七次实验，还一度被误判成"模型不想用"。
function RefreshTools({ name, online }: { name: string; online: boolean }) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  if (!online) return null;
  return (
    <span className="flex items-center gap-1">
      {msg && <span className="text-[11px] text-neutral-400">{msg}</span>}
      <button
        disabled={busy}
        title={t("If the world changed its tools or restarted, click this to make the brain ask again (the capability list is cached at handshake)")}
        onClick={async () => {
          setBusy(true);
          setMsg(t("Re-handshaking…"));
          const r = await refreshWorld(name).catch(() => ({ ok: false, message: t("Cannot reach the backend") }));
          setMsg(r.message ?? "");
          setBusy(false);
        }}
        className="rounded border border-neutral-700 bg-neutral-800 px-2 py-0.5 text-[11px] text-neutral-300 hover:bg-neutral-700 disabled:opacity-50"
      >
        {t("Re-handshake")}
      </button>
    </span>
  );
}

// 🧠 Engine Server 卡：ANIMA 请教的引擎顾问（由 ANIMA 按 config.services() 挂载）——只渲染它真有的东西：状态、工具。
// 没有画面、没有说明书就不渲染那两栏（顾问=纯计算，本来就没有）。
function ServiceCard({ s }: { s: AwiService }) {
  const { t } = useI18n();
  return (
    <div className="rounded-xl border border-emerald-900/60 bg-neutral-900 p-4">
      <div className="flex items-center justify-between">
        <span className="font-medium">
          🧠 {s.name} <span className="text-xs text-neutral-500">{t("Engine Server · a pure-computation advisor ANIMA consults")}</span>
        </span>
        <span className={`text-xs ${s.online ? "text-green-400" : "text-red-400"}`}>● {s.online ? t("online") : t("offline")}</span>
      </div>
      <div className="mt-1 text-[11px] text-neutral-500">
        {s.url}
        <span>{t(" · mounted by ANIMA from its own config (standard MCP host assembly)")}</span>
      </div>
      <div className="mt-3">
        <Region title="Tools" color="#34d399" sub={t("Ask and get an answer: give it a well-formed question, it replies")}>
          {s.tools.map((t) => (
            <CapCard key={t.name} name={t.name} kind={(t as AwiTool).kind} desc={t.description}
              schema={t.parameters} accent="text-emerald-300" />
          ))}
          {s.tools.length === 0 && (
            <div className="text-xs text-neutral-500">{s.online ? t("(no tools declared)") : t("(offline — tool list unavailable)")}</div>
          )}
        </Region>
      </div>
    </div>
  );
}

// embedded=true：内嵌在主页中间区（h-full 滚动、隐藏顶部回主界面导航）；false：作为 /awi 整页独立版。
// onOpenLogs：内嵌时点正文里的 Session Logs 链接 → 切到内嵌 logs 视图（而非整页跳出 SPA）。
export default function AwiDashboard({ embedded = false, onOpenLogs }: { embedded?: boolean; onOpenLogs?: () => void }) {
  const { t } = useI18n();
  const [data, setData] = useState<AwiOverview | null>(null);
  const [events, setEvents] = useState<Ev[]>([]);
  const termRef = useRef<HTMLDivElement>(null);

  // ?live=0：不开实时流量那条 SSE 长连接。
  // 用途一是把这块嵌进文档/看板时不该一直占着连接；用途二是**出文档截图**——
  // headless 浏览器只要页面上还挂着一条不结束的连接就永远等不到"加载完成",
  // 一张图都截不出来（2026-07-27 实测：挂满 240 秒无输出）。
  const liveTraffic = typeof window === "undefined"
    || new URLSearchParams(window.location.search).get("live") !== "0";

  useEffect(() => {
    const load = () => getAwi().then(setData).catch(() => {});
    load();
    const id = setInterval(load, OVERVIEW_POLL_MS);
    if (!liveTraffic) return () => clearInterval(id);
    const es = new EventSource(awiEventsUrl());
    es.onmessage = (e) => setEvents((prev) => [...prev.slice(-AWI_LOG_SHOWN), JSON.parse(e.data) as Ev]);
    return () => {
      clearInterval(id);
      es.close();
    };
  }, [liveTraffic]);
  useEffect(() => {
    termRef.current?.scrollTo(0, termRef.current.scrollHeight);
  }, [events]);

  const services = data?.services ?? [];

  return (
    <main className={`${embedded ? "h-full min-w-0 overflow-y-auto" : "min-h-screen"} bg-neutral-950 p-6 text-neutral-200`}>
      <div className="mx-auto max-w-6xl space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold">{t("AWI dashboard · Anima World Interface")}</h1>
          {!embedded && (
            <div className="space-x-3 text-sm">
              <a href="/session-logs" className="text-blue-400 hover:underline">{t("Session Logs (activity trace)")}</a>
              <a href="/" className="text-blue-400 hover:underline">{t("← Back to the app")}</a>
            </div>
          )}
        </div>

        {/* 一句人话说明 + 细节全部折叠（想深究再点开） */}
        <p className="text-sm leading-relaxed text-neutral-400">
          {t("ANIMA (the host) connects to two kinds of MCP server: ")}<b className="text-neutral-200">🌍 World Server</b>{t(" — the reality it inhabits (it has a camera; actions change that reality); ")}
          <b className="text-neutral-200">🧠 Engine Server</b>{t(" — advisors it consults (pure computation, question in / answer out, mounted by ANIMA from its own config).")}
          {t("This page shows the contract and live traffic of those connections. For the full chain of what ANIMA saw, thought and called, see")}{" "}
          {embedded && onOpenLogs ? (
            <button onClick={onOpenLogs} className="text-blue-400 hover:underline">Session Logs</button>
          ) : (
            <a href="/session-logs" className="text-blue-400 hover:underline">Session Logs</a>
          )}
          。
        </p>
        <details className="text-xs leading-relaxed text-neutral-500">
          <summary className="cursor-pointer text-neutral-400">{t("How to read this page (MCP details — click to open)")}</summary>
          <div className="mt-2 space-y-2">
            <p>
              {t("The interface is standard MCP. ANIMA is the initiator (the host), and servers come in two kinds \u2014 World Server and Engine Server. The brain always initiates and the server answers; the host opens one dedicated line per server (RemoteWorld / RemoteService in the code, MCP\u2019s client layer). Each server describes itself with MCP\u2019s three primitives: Tools (tools/call \u2014 actions or questions), Resources (resources/read anima://observation \u2014 a snapshot and structured state) and Prompts (prompts/get guidance \u2014 the guidance). A World Server has all three; an Engine Server has only tools, since an adviser does not perceive the world. Which servers to connect is assembled by ANIMA (the host) from its own configuration \u2014 config.worlds() / config.services() \u2014 so servers do not know one another, and a World Server never declares an Engine Server.")}
            </p>
            <p>
              {t("Each World Server card also folds away a few side channels that never travel over MCP and exist for people only: /status (ground truth for debugging, the god\u2019s-eye view), /stream (continuous video) and /health (liveness, about every {sec}s; not counted in the live traffic below, which would otherwise be nothing else — that traffic is only real brain-to-server calls).", { sec: OVERVIEW_POLL_MS / 1000 })}
            </p>
          </div>
        </details>

        {data && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="World Server" value={data.worlds.length} />
            <Stat label="Engine Server" value={services.length} />
            <Stat label={t("online")} value={data.worlds.filter((w) => w.online).length + services.filter((s) => s.online).length} />
            <Stat label={t("Total calls")} value={data.stats.total} />
          </div>
        )}

        <section>
          <h2 className="mb-2 text-sm font-medium text-neutral-400">🌍 World Server <span className="text-xs font-normal text-neutral-600">{t("· the reality ANIMA inhabits — one per session")}</span></h2>
          <div className="space-y-3">
            {data?.worlds.map((w) => <WorldCard key={`w:${w.name}`} w={w} />)}
          </div>
        </section>

        <section>
          <h2 className="mb-2 text-sm font-medium text-neutral-400">🧠 Engine Server <span className="text-xs font-normal text-neutral-600">{t("· advisors ANIMA consults, mounted from its own config (host assembly)")}</span></h2>
          <div className="space-y-3">
            {services.map((s) => <ServiceCard key={`s:${s.url}`} s={s} />)}
            {services.length === 0 && (
              <div className="rounded-xl border border-neutral-800 bg-neutral-900 p-4 text-xs text-neutral-500">
                {t("(none — ANIMA's service list config.services() is empty)")}
              </div>
            )}
          </div>
        </section>

        <section>
          <h2 className="mb-2 text-sm font-medium text-neutral-400">{t("Live traffic")} <span className="text-xs font-normal text-neutral-600">{t("· every call between ANIMA and a World/Engine Server (over MCP)")}</span></h2>
          <p className="mb-2 text-xs leading-relaxed text-neutral-500">
            {t("Two halves per line: ")}<span className="text-neutral-300">{t("→ sent")}</span>{t(" (command + arguments), ")}<span className="text-neutral-300">{t("← returned")}</span>{t(" (image bytes, success/failure, returned state, answer).")}
            {t("Audit point: the state returned by perceive must never smuggle in the world\u2019s ground truth (a FEN, the position, the moves) \u2014 anything that looks like ground truth is flagged \u26a0.")}
          </p>
          <div
            ref={termRef}
            className="h-80 overflow-y-auto rounded-xl border border-neutral-800 bg-black p-3 font-mono text-xs leading-relaxed"
          >
            {events.length === 0 && (
              <div className="text-neutral-600">{t("(no traffic yet — send a message in the app, or poke the world in its own UI)")}</div>
            )}
            {events.map((e) => {
              const inb = fmtResp(e.method, e.resp);
              return (
                <div key={e.id} className="mb-1">
                  <div>
                    <span className="text-neutral-600">[{e.ts}]</span>{" "}
                    <span className="text-neutral-500">{e.world}</span>{" "}
                    <span className={METHOD_COLOR[e.method] ?? "text-neutral-300"}>{e.method}</span>{" "}
                    <span className="text-blue-400">→</span>
                    <span className="text-neutral-300"> {e.summary}</span>
                    <span className="text-neutral-600"> ({e.ms}ms)</span>
                    {e.session && <span className="text-neutral-700"> ·{e.session.slice(0, 10)}</span>}
                  </div>
                  <div className="pl-14">
                    <span className="text-fuchsia-400">←</span>
                    <span className={inb.warn ? "text-amber-400" : "text-neutral-400"}> {inb.text}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        <div className="grid gap-4 md:grid-cols-2">
          <section>
            <h2 className="mb-2 text-sm font-medium text-neutral-400">{t("Brain interface (LLM)")}</h2>
            <div className="space-y-1.5">
              {data?.brains.map((b) => (
                <div
                  key={b.name}
                  className="flex items-center justify-between rounded-lg border border-neutral-800 bg-neutral-900 px-3 py-2 text-xs"
                >
                  <span>
                    {t(b.vendor)} · <b>{t(b.label)}</b> <span className="text-neutral-500">({b.model})</span>
                  </span>
                  <span className={b.available ? "text-green-400" : "text-neutral-500"}>
                    {b.available ? t("configured") : t("not configured")}
                  </span>
                </div>
              ))}
            </div>
          </section>
          <section>
            <h2 className="mb-2 text-sm font-medium text-neutral-400">{t("Sessions")}</h2>
            <div className="space-y-1.5">
              {data?.sessions.length === 0 && <div className="text-xs text-neutral-500">{t("(no sessions yet)")}</div>}
              {data?.sessions.map((s) => (
                <div
                  key={s.id}
                  className="flex items-center justify-between rounded-lg border border-neutral-800 bg-neutral-900 px-3 py-2 text-xs"
                >
                  <span className="truncate">
                    {s.title}　<span className="text-neutral-500">{s.world ?? t("Chat only")} · {s.brain}</span>
                  </span>
                  <span className={s.status === "active" ? "text-green-400" : "text-amber-500"}>
                    {s.status === "active" ? t("running") : t("🔒 read-only")}
                  </span>
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}
