"use client";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { getAwi, awiEventsUrl, AWI_LOG_SHOWN, POLL_AWI_MS, type AwiOverview } from "@/lib/api";

// 回方向(世界→ANIMA)的结构化返回；不同 method 用不同字段
type Resp = {
  n_tools?: number;
  tools?: string[];
  img_bytes?: number;
  state?: Record<string, unknown>;
  ok?: boolean;
  message?: string;
  has_data?: boolean;
};
type Ev = { id: number; ts: string; world: string; method: string; summary: string; resp?: Resp; ms: number };

const OVERVIEW_POLL_MS = POLL_AWI_MS; // /api/awi 概览多久刷一次（env 可覆盖）

const METHOD_COLOR: Record<string, string> = {
  capabilities: "text-purple-400",
  perceive: "text-cyan-400",
  invoke: "text-green-400",
};

// ---- /awi 世界卡片：风格2「色条分区」。TOOLS/STATE 同构卡片：描述 + 原始 schema/内容（不渲染花哨色子）----
// 原始 JSON 代码块（直接展示 schema / 内容，所见即所得）
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
  return (
    <div className="rounded-md border border-neutral-800 bg-neutral-950/50 p-2">
      <div className="flex items-center gap-2">
        <span className={`font-mono text-[13px] ${accent}`}>{name}</span>
        {kind && <span className="rounded bg-neutral-800 px-1.5 py-0.5 text-[10px] text-neutral-400">{kind}</span>}
      </div>
      {desc && <div className="mt-0.5 text-[12px] text-neutral-400">{desc}</div>}
      {schema !== undefined && (
        <details className="mt-0.5">
          <summary className="cursor-pointer text-[10px] text-neutral-500">schema / 内容</summary>
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

// 把回方向(世界→ANIMA)格式化成一句人话；perceive 的回程 state 是审计点：
// 现在 state 允许带【角色 meta】(如 controllers=谁坐哪一方)，但红线仍是【绝不许夹带棋盘真值】(FEN/局面/着法)。
// 所以非空不再一律告警；只有当 state 看起来含棋盘真值时才标 ⚠，请人工确认。
function fmtResp(method: string, resp?: Resp): { text: string; warn: boolean } {
  if (!resp) return { text: "(无)", warn: false };
  if (method === "capabilities")
    return { text: `${resp.n_tools ?? 0} 个能力 [${(resp.tools ?? []).join(", ")}]`, warn: false };
  if (method === "perceive") {
    const st = resp.state ?? {};
    const blob = JSON.stringify(st);
    // 启发式：含 fen/board/pieces/legal 或 FEN 样式(行间 '/') → 疑似棋盘真值
    const looksLikeTruth = /fen|"board"|pieces|legal|[pnbrqkPNBRQK1-8]+\/[pnbrqkPNBRQK1-8]+/.test(blob);
    return {
      text: `图片 ${resp.img_bytes ?? 0} 字节 · 回程 state: ${blob}${looksLikeTruth ? " (⚠ 疑似夹带棋盘真值)" : " (未见棋盘真值 ✓)"}`,
      warn: looksLikeTruth,
    };
  }
  if (method === "invoke")
    return {
      text: `${resp.ok ? "ok ✓" : "FAIL ✗"} · ${resp.message ?? ""}${resp.has_data ? " · ⚠ 回了 data" : ""}`,
      warn: !!resp.has_data,
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

// embedded=true：内嵌在主页中间区（h-full 滚动、隐藏顶部回主界面导航）；false：作为 /awi 整页独立版。
// onOpenLogs：内嵌时点正文里的 anima-logs 链接 → 切到内嵌 logs 视图（而非整页跳出 SPA）。
export default function AwiDashboard({ embedded = false, onOpenLogs }: { embedded?: boolean; onOpenLogs?: () => void }) {
  const [data, setData] = useState<AwiOverview | null>(null);
  const [events, setEvents] = useState<Ev[]>([]);
  const termRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const load = () => getAwi().then(setData).catch(() => {});
    load();
    const id = setInterval(load, OVERVIEW_POLL_MS);
    const es = new EventSource(awiEventsUrl());
    es.onmessage = (e) => setEvents((prev) => [...prev.slice(-AWI_LOG_SHOWN), JSON.parse(e.data) as Ev]);
    return () => {
      clearInterval(id);
      es.close();
    };
  }, []);
  useEffect(() => {
    termRef.current?.scrollTo(0, termRef.current.scrollHeight);
  }, [events]);

  return (
    <main className={`${embedded ? "h-full min-w-0 overflow-y-auto" : "min-h-screen"} bg-neutral-950 p-6 text-neutral-200`}>
      <div className="mx-auto max-w-6xl space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold">AWI 仪表盘 · Anima World Interface</h1>
          {!embedded && (
            <div className="space-x-3 text-sm">
              <a href="/anima-logs" className="text-blue-400 hover:underline">anima-logs（脑↔大模型）</a>
              <a href="/" className="text-blue-400 hover:underline">← 回主界面</a>
            </div>
          )}
        </div>
        <p className="text-sm leading-relaxed text-neutral-400">
          AWI 是「脑 ↔ 世界」的接口标准——全程 <b>脑发起、世界应答</b>（纯拉取，世界不主动推）。
          <b className="text-neutral-200">核心跨线动作</b>（协议骨架，每个世界都一样）：
          <code className="mx-1 rounded bg-neutral-800 px-1">capabilities</code>(声明 tools)、
          <code className="mx-1 rounded bg-neutral-800 px-1">perceive</code>(看：画面 + 结构化 state)、
          <code className="mx-1 rounded bg-neutral-800 px-1">invoke</code>(调一个 tool，如 take_seat / start_game / move / resign)。
          下面每张世界卡片分三区：<b className="text-neutral-200">TOOLS</b>(能力) / <b className="text-neutral-200">STATE</b>(随画面给脑的结构化状态) / <b className="text-neutral-200">STATUS</b>(仅人看的调试真值·上帝视角)，都是"<b>这个世界</b>声明/持有的"，各世界各异。
        </p>
        <p className="text-xs leading-relaxed text-neutral-500">
          注意：<b>skill（剧本）和行为树是 ANIMA 脑内的结构、不在 AWI 线上</b>（世界根本不知道它们存在），所以这里看不到——
          要看 ANIMA 的思考（进入判定 / 解说 / 意图分类…）请去{" "}
          {embedded && onOpenLogs ? (
            <button onClick={onOpenLogs} className="text-blue-400 hover:underline">anima-logs</button>
          ) : (
            <a href="/anima-logs" className="text-blue-400 hover:underline">anima-logs</a>
          )}
          。
        </p>
        <p className="text-xs leading-relaxed text-neutral-500">
          另外世界还提供一个轻量探活端点
          <code className="mx-1 rounded bg-neutral-800 px-1">GET /health</code>:这个仪表盘<b>每约 {OVERVIEW_POLL_MS / 1000} 秒</b>探一次,
          用它判断世界在不在线——就是下面每张世界卡片右上角的状态点:
          <span className="text-green-400">● 在线</span> / <span className="text-red-400">● 离线</span>。
          它<b>不计入下面的「AWI 实时流量」</b>——故意的,免得每隔几秒的探活把流量刷屏。真正的脑↔世界调用(capabilities / perceive / invoke)才会出现在流量里。
        </p>

        {data && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="AWI 总调用" value={data.stats.total} />
            <Stat label="世界" value={data.worlds.length} />
            <Stat
              label="大脑(已配置 / 总)"
              value={`${data.brains.filter((b) => b.available).length}/${data.brains.length}`}
            />
            <Stat label="会话" value={data.sessions.length} />
          </div>
        )}

        <section>
          <h2 className="mb-2 text-sm font-medium text-neutral-400">已连接的世界（它声明的 tools）</h2>
          <div className="space-y-3">
            {data?.worlds.map((w) => (
              <div key={w.name} className="rounded-xl border border-neutral-800 bg-neutral-900 p-4">
                <div className="flex items-center justify-between">
                  <span className="font-medium">
                    🌐 {w.name} <span className="text-xs text-neutral-500">v{w.version}</span>
                  </span>
                  <span className={`text-xs ${w.online ? "text-green-400" : "text-red-400"}`}>
                    ● {w.online ? "在线" : "离线"}
                  </span>
                </div>
                <div className="mt-1 text-[11px] text-neutral-500">{w.url}</div>

                {/* 风格2 · 色条分区：TOOLS(绿) / STATE(蓝) / STATUS(紫)——三个独立指标区 */}
                <div className="mt-3 space-y-3">
                  <Region title="TOOLS" color="#3fb950" sub="世界声明、ANIMA 调用的能力（含 schema）">
                    {w.tools.map((t) => (
                      <CapCard key={t.name} name={t.name} kind={t.kind} desc={t.description}
                        schema={t.parameters} accent="text-green-300" />
                    ))}
                    {w.tools.length === 0 && <div className="text-xs text-neutral-500">(离线，拿不到能力)</div>}
                  </Region>

                  <Region title="STATE" color="#58a6ff" sub="随画面给脑的结构化 state（脑能看）——世界声明的契约，绝不含棋盘真值">
                    {!w.online ? (
                      <div className="text-xs text-neutral-500">(离线，拿不到 state)</div>
                    ) : (
                      <CapCard name="perceive.state" kind="给脑 · 随画面" accent="text-sky-300"
                        desc="世界经 perceive 随画面给 ANIMA 的结构化状态。下面是世界【声明】的契约（键→含义），由模块声明、不是缓存的上次值；绝不含棋盘真值。"
                        schema={w.state_schema && Object.keys(w.state_schema).length ? w.state_schema : (w.state ?? {})} />
                    )}
                  </Region>

                  <Region title="STATUS" color="#a371f7" sub="仅人看的调试真值（上帝视角）——走世界本地 /status，绝不进 perceive、ANIMA 看不到">
                    {!w.online ? (
                      <div className="text-xs text-neutral-500">(离线，拿不到 status)</div>
                    ) : (() => {
                      const truth = JSON.stringify(w.status ?? {});
                      const has = w.status != null && truth !== "{}" && truth !== "null";
                      return has ? (
                        <CapCard name="🔒 调试真值（上帝视角）" kind="仅人看 · 非 perceive" accent="text-neutral-300"
                          desc="世界本地的完整真值，只给人看的调试台、不进 perceive——ANIMA 看不到（棋类世界里如 FEN / 棋子真实位置）"
                          schema={w.status ?? {}} />
                      ) : (
                        <div className="text-xs text-neutral-500">(此世界没有 /status 上帝视角，如 sim-desk)</div>
                      );
                    })()}
                  </Region>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section>
          <h2 className="mb-2 text-sm font-medium text-neutral-400">AWI 实时流量(双向:ANIMA → 世界 / 世界 → ANIMA)</h2>
          <p className="mb-2 text-xs leading-relaxed text-neutral-500">
            每条都拆成两半:<span className="text-neutral-300">→ 出方向</span>(ANIMA 发的命令+参数)、
            <span className="text-neutral-300">← 回方向</span>(世界返回的:图片字节数、ok/message、回程 state)。
            <b className="text-neutral-400">审计点</b>:<code className="rounded bg-neutral-800 px-1">perceive</code> 的回程 state 可含<b>角色 meta</b>
            (如 controllers=谁坐哪一方),但<b>绝不许夹带棋盘真值</b>(FEN/局面/着法);疑似含真值才标 <span className="text-amber-400">⚠</span>,请人工确认。
            (世界的完整真值在上面每张卡片的<b>「真值(调试)」</b>里——那是走 /status 的人类上帝视角,ANIMA 看不到。)
          </p>
          <div
            ref={termRef}
            className="h-80 overflow-y-auto rounded-xl border border-neutral-800 bg-black p-3 font-mono text-xs leading-relaxed"
          >
            {events.length === 0 && (
              <div className="text-neutral-600">(暂无流量;去主界面发条消息,或在世界自己的界面里操作一下)</div>
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
            <h2 className="mb-2 text-sm font-medium text-neutral-400">大脑接口(LLM)</h2>
            <div className="space-y-1.5">
              {data?.brains.map((b) => (
                <div
                  key={b.name}
                  className="flex items-center justify-between rounded-lg border border-neutral-800 bg-neutral-900 px-3 py-2 text-xs"
                >
                  <span>
                    {b.vendor} · <b>{b.label}</b> <span className="text-neutral-500">({b.model})</span>
                  </span>
                  <span className={b.available ? "text-green-400" : "text-neutral-500"}>
                    {b.available ? "已配置" : "未配置"}
                  </span>
                </div>
              ))}
            </div>
          </section>
          <section>
            <h2 className="mb-2 text-sm font-medium text-neutral-400">会话</h2>
            <div className="space-y-1.5">
              {data?.sessions.length === 0 && <div className="text-xs text-neutral-500">(暂无会话)</div>}
              {data?.sessions.map((s) => (
                <div
                  key={s.id}
                  className="flex items-center justify-between rounded-lg border border-neutral-800 bg-neutral-900 px-3 py-2 text-xs"
                >
                  <span className="truncate">
                    {s.title}　<span className="text-neutral-500">{s.world ?? "纯聊天"} · {s.brain}</span>
                  </span>
                  <span className={s.status === "active" ? "text-green-400" : "text-amber-500"}>
                    {s.status === "active" ? "进行中" : "🔒只读"}
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
