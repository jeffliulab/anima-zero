"use client";
import { useEffect, useRef, useState } from "react";
import { getAwi, awiEventsUrl, AWI_LOG_SHOWN, type AwiOverview } from "@/lib/api";

type Ev = { id: number; ts: string; world: string; method: string; summary: string; ms: number };

const OVERVIEW_POLL_MS = 3000; // /api/awi 概览多久刷一次

const METHOD_COLOR: Record<string, string> = {
  capabilities: "text-purple-400",
  perceive: "text-cyan-400",
  invoke: "text-green-400",
};

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-neutral-800 bg-neutral-900 p-3">
      <div className="text-2xl font-semibold">{value}</div>
      <div className="text-xs text-neutral-500">{label}</div>
    </div>
  );
}

export default function AwiDashboard() {
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
    <main className="min-h-screen bg-neutral-950 p-6 text-neutral-200">
      <div className="mx-auto max-w-6xl space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold">AWI 仪表盘 · Anima World Interface</h1>
          <a href="/" className="text-sm text-blue-400 hover:underline">← 回主界面</a>
        </div>
        <p className="text-sm leading-relaxed text-neutral-400">
          AWI 是「脑 ↔ 世界」的接口标准。任何「世界」实现这四个端点就能接入 ANIMA:
          <code className="mx-1 rounded bg-neutral-800 px-1">GET /capabilities</code>(声明能力)、
          <code className="mx-1 rounded bg-neutral-800 px-1">GET /perceive</code>(看)、
          <code className="mx-1 rounded bg-neutral-800 px-1">POST /invoke</code>(动)、
          <code className="mx-1 rounded bg-neutral-800 px-1">POST /reset</code>(世界自复位)。
          下面是当前所有连接、能力、实时流量。
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
          <h2 className="mb-2 text-sm font-medium text-neutral-400">已连接的世界(及其 skill)</h2>
          <div className="grid gap-3 md:grid-cols-2">
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
                <div className="mt-1 text-[11px] text-neutral-500">
                  {w.url}　·　state: {JSON.stringify(w.state)}
                </div>
                <div className="mt-3 space-y-1.5">
                  {w.tools.map((t) => (
                    <div key={t.name} className="rounded-lg bg-neutral-800/60 p-2 text-xs">
                      <span className="font-mono text-green-300">{t.name}</span>
                      <span className="ml-2 rounded bg-neutral-700 px-1.5 py-0.5 text-[10px] text-neutral-300">
                        {t.kind}
                      </span>
                      <div className="mt-0.5 text-neutral-400">{t.description}</div>
                      <div className="mt-0.5 text-[10px] text-neutral-600">参数:{JSON.stringify(t.parameters)}</div>
                    </div>
                  ))}
                  {w.tools.length === 0 && <div className="text-xs text-neutral-500">(离线,拿不到能力)</div>}
                </div>
              </div>
            ))}
          </div>
        </section>

        <section>
          <h2 className="mb-2 text-sm font-medium text-neutral-400">AWI 实时流量(ANIMA ↔ 世界)</h2>
          <div
            ref={termRef}
            className="h-72 overflow-y-auto rounded-xl border border-neutral-800 bg-black p-3 font-mono text-xs leading-relaxed"
          >
            {events.length === 0 && (
              <div className="text-neutral-600">(暂无流量;去主界面发条消息,或在世界自己的界面里操作一下)</div>
            )}
            {events.map((e) => (
              <div key={e.id}>
                <span className="text-neutral-600">[{e.ts}]</span>{" "}
                <span className="text-neutral-500">{e.world}</span>{" "}
                <span className={METHOD_COLOR[e.method] ?? "text-neutral-300"}>{e.method}</span>
                <span className="text-neutral-300"> {e.summary}</span>
                <span className="text-neutral-600"> ({e.ms}ms)</span>
              </div>
            ))}
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
