"use client";
import { useEffect, useState } from "react";

// 中间传感区：嵌世界的实时画面(MJPEG)，多相机一等公民。
// - 世界暴露 GET /streams（[{name,url}]）→ 有几路就并列展示几路（各带相机名标签）；
//   没有该端点的世界回退单路 /stream（零改动）。
// - 按钮组 [全部] [相机A] [相机B]…：「全部」=并列网格；选某一路=固定放大那一路。
//   选择只由人点按钮改变——结构上不存在任何自动切换（坚决杜绝画面来回闪）。
// 断连判定：先用后端给的 online 作初值(秒级反馈)，再以第一路 <img> 实际能否加载为准。
type Cam = { name: string; url: string };

const ALL = ""; // 选中值空串 = 全部并列

export default function SensingArea({
  worldUrl,
  worldName,
  online,
}: {
  worldUrl: string | null;
  worldName: string | null;
  online: boolean | null; // null = 纯聊天/无世界
}) {
  const [cams, setCams] = useState<Cam[]>([]);
  const [selected, setSelected] = useState<string>(ALL);
  const [failed, setFailed] = useState(false);
  const [nonce, setNonce] = useState(0); // 点"重试"时 +1，强制 <img> 重新连

  // 发现这个世界有几路相机：/streams 有就用（并列），没有（404/网络错）回退单 /stream。
  useEffect(() => {
    setSelected(ALL);
    if (!worldUrl) {
      setCams([]);
      return;
    }
    let stop = false;
    const fallback: Cam[] = [{ name: "", url: `${worldUrl}/stream` }];
    fetch(`${worldUrl}/streams`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((list: { name: string; url: string }[]) => {
        if (stop) return;
        const abs = (u: string) => (u.startsWith("http") ? u : `${worldUrl}${u}`);
        setCams(list.length ? list.map((c) => ({ name: c.name, url: abs(c.url) })) : fallback);
      })
      .catch(() => {
        if (!stop) setCams(fallback);
      });
    return () => {
      stop = true;
    };
  }, [worldUrl, nonce]);

  // 切换世界 / 点重试 / 后端在线状态变化 → 重置：以 online 作断连初值，之后交给 img 的 onLoad/onError 校正
  useEffect(() => {
    setFailed(online === false);
  }, [worldUrl, online, nonce]);

  const disconnected = !!worldName && !!worldUrl && failed;
  const shown = selected === ALL ? cams : cams.filter((c) => c.name === selected);
  const multi = cams.length > 1;

  return (
    <section className="flex min-w-0 flex-col gap-3 overflow-hidden p-6">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-medium text-neutral-400">
          传感区 · ANIMA 看到的画面{worldName ? `（${worldName} · 实时）` : ""}
        </h2>
        {multi && (
          <div className="ml-auto flex items-center gap-1">
            <button
              onClick={() => setSelected(ALL)}
              className={`rounded-md border px-2 py-1 text-[11px] ${selected === ALL ? "border-blue-500 bg-blue-600/20 text-blue-300" : "border-neutral-700 bg-neutral-800 text-neutral-300 hover:bg-neutral-700"}`}
            >
              全部
            </button>
            {cams.map((c) => (
              <button
                key={c.name}
                onClick={() => setSelected(c.name)}
                className={`rounded-md border px-2 py-1 font-mono text-[11px] ${selected === c.name ? "border-blue-500 bg-blue-600/20 text-blue-300" : "border-neutral-700 bg-neutral-800 text-neutral-300 hover:bg-neutral-700"}`}
              >
                {c.name || "默认"}
              </button>
            ))}
          </div>
        )}
      </div>
      <div className="relative flex-1 overflow-hidden">
        {!worldUrl ? (
          <div className="flex h-full items-center justify-center rounded-2xl border border-neutral-800 bg-neutral-900">
            <span className="text-sm text-neutral-500">纯聊天 / 未连接世界</span>
          </div>
        ) : (
          <>
            <div className={`grid h-full gap-3 ${shown.length > 1 ? "grid-cols-2 content-center" : "grid-cols-1"}`}>
              {shown.map((c, i) => (
                <div
                  key={`${c.name}#${nonce}`}
                  className="relative flex min-h-0 items-center justify-center overflow-hidden rounded-2xl border border-neutral-800 bg-neutral-900"
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={c.url}
                    alt={c.name ? `相机 ${c.name}` : "世界实时画面"}
                    onLoad={i === 0 ? () => setFailed(false) : undefined}
                    onError={i === 0 ? () => setFailed(true) : undefined}
                    className={`max-h-full max-w-full rounded-xl transition-opacity ${disconnected ? "opacity-10" : "opacity-100"}`}
                  />
                  {c.name && (
                    <span className="absolute left-2 top-2 rounded bg-neutral-950/70 px-1.5 py-0.5 font-mono text-[10px] text-neutral-300">
                      {c.name}
                    </span>
                  )}
                </div>
              ))}
            </div>
            {disconnected && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 rounded-2xl bg-neutral-950/70 p-6 text-center">
                <div className="text-3xl">🔌</div>
                <div className="text-sm font-medium text-amber-400">未连接到世界「{worldName}」</div>
                <div className="max-w-xs text-xs leading-relaxed text-neutral-400">
                  收不到这个世界的画面。请确认它的进程已启动（见项目根目录的{" "}
                  <code className="rounded bg-neutral-800 px-1">运行命令.md</code>），
                  起好后点下面重试。
                </div>
                <button
                  onClick={() => setNonce((n) => n + 1)}
                  className="mt-1 rounded-lg bg-amber-600/80 px-3 py-1.5 text-xs text-white hover:bg-amber-600"
                >
                  重试连接
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
