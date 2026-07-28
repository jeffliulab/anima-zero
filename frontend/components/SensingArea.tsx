"use client";
import { useEffect, useState } from "react";

import { useI18n } from "@/lib/i18n";

// 中间传感区：嵌世界的实时画面(MJPEG)，多相机一等公民。
// - 世界暴露 GET /streams（[{name,url,awi?}]）→ 有几路就展示几路（各带相机名标签）；
//   没有该端点的世界回退单路 /stream（零改动）。
// - 按钮组 [全部] [相机A] [相机B]…：「全部」=并列网格；选某一路=固定放大那一路。
//   选择只由人点按钮改变——结构上不存在任何自动切换（坚决杜绝画面来回闪）。
// 断连判定：先用后端给的 online 作初值(秒级反馈)，再以第一路 <img> 实际能否加载为准。
//
// ⛔ **`awi` 字段决定这一路摆在哪一块**（v1.0）：true/没写 = ANIMA 真正看到的画面；
//    false = 只给人看的旁观视角（如第三视角跟拍）。两块分开、各有各的标题——
//    把跟拍画面摆在「ANIMA 看到的画面」底下就是**撒谎**，会让人以为大脑有上帝视角。
type Cam = { name: string; url: string; awi: boolean };

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
  const { t } = useI18n();
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
    const fallback: Cam[] = [{ name: "", url: `${worldUrl}/stream`, awi: true }];
    fetch(`${worldUrl}/streams`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((list: { name: string; url: string; awi?: boolean }[]) => {
        if (stop) return;
        const abs = (u: string) => (u.startsWith("http") ? u : `${worldUrl}${u}`);
        // awi 没写就按 true——老世界没有这个字段，它们的画面本来就都是大脑看到的。
        setCams(list.length
          ? list.map((c) => ({ name: c.name, url: abs(c.url), awi: c.awi !== false }))
          : fallback);
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
  // 两块：大脑看得见的 / 只有你看得见的。分开摆、各有各的标题（见文件头的红线说明）。
  const brainCams = shown.filter((c) => c.awi);
  const humanCams = shown.filter((c) => !c.awi);

  return (
    <section className="flex min-w-0 flex-col gap-3 overflow-hidden p-6">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-medium text-neutral-400">
          {t("Sensors")}
          {worldName ? `（${worldName} · ${t("live")}）` : ""}
        </h2>
        {multi && (
          <div className="ml-auto flex items-center gap-1">
            <button
              onClick={() => setSelected(ALL)}
              className={`rounded-md border px-2 py-1 text-[11px] ${selected === ALL ? "border-blue-500 bg-blue-600/20 text-blue-300" : "border-neutral-700 bg-neutral-800 text-neutral-300 hover:bg-neutral-700"}`}
            >
              {t("All")}
            </button>
            {cams.map((c) => (
              <button
                key={c.name}
                onClick={() => setSelected(c.name)}
                className={`rounded-md border px-2 py-1 font-mono text-[11px] ${selected === c.name ? "border-blue-500 bg-blue-600/20 text-blue-300" : "border-neutral-700 bg-neutral-800 text-neutral-300 hover:bg-neutral-700"}`}
              >
                {c.name || t("default")}
              </button>
            ))}
          </div>
        )}
      </div>
      <div className="relative flex-1 overflow-hidden">
        {!worldUrl ? (
          <div className="flex h-full items-center justify-center rounded-2xl border border-neutral-800 bg-neutral-900">
            <span className="text-sm text-neutral-500">{t("Chat only / no world connected")}</span>
          </div>
        ) : (
          <>
            <div className="flex h-full min-h-0 flex-col gap-2">
              <CamGroup
                title={t("👁 What ANIMA sees")}
                cams={brainCams}
                nonce={nonce}
                disconnected={disconnected}
                onFirstLoad={setFailed}
              />
              {humanCams.length > 0 && (
                <CamGroup
                  title={t("🎥 Third-person — for you only, ANIMA cannot see this")}
                  cams={humanCams}
                  nonce={nonce}
                  disconnected={disconnected}
                  muted
                />
              )}
            </div>
            {disconnected && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 rounded-2xl bg-neutral-950/70 p-6 text-center">
                <div className="text-3xl">🔌</div>
                <div className="text-sm font-medium text-amber-400">{t("Not connected to world “{name}”", { name: worldName ?? "" })}</div>
                <div className="max-w-xs text-xs leading-relaxed text-neutral-400">
                  {t("No video from this world. Make sure its process is running (see")}{" "}
                  <code className="rounded bg-neutral-800 px-1">{t("the run-commands doc")}</code>
                  {t(") and then retry below.")}
                </div>
                <button
                  onClick={() => setNonce((n) => n + 1)}
                  className="mt-1 rounded-lg bg-amber-600/80 px-3 py-1.5 text-xs text-white hover:bg-amber-600"
                >
                  {t("Retry connection")}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}

// 一组画面 + 它的标题。分组的意义全在标题上：⛔「ANIMA 看到的」和「只有你看得到的」
// 必须视觉上分开，否则用户会以为大脑也有那个上帝视角。
// muted = 这一组是旁观视角，画面压暗一点、标题用灰色，一眼看出它不是主角。
function CamGroup({
  title,
  cams,
  nonce,
  disconnected,
  onFirstLoad,
  muted = false,
}: {
  title: string;
  cams: { name: string; url: string; awi: boolean }[];
  nonce: number;
  disconnected: boolean;
  onFirstLoad?: (failed: boolean) => void;
  muted?: boolean;
}) {
  const { t } = useI18n();
  if (!cams.length) return null;
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-1">
      <div className={`text-[11px] ${muted ? "text-neutral-600" : "text-neutral-400"}`}>{title}</div>
      <div className={`grid min-h-0 flex-1 gap-3 ${cams.length > 1 ? "grid-cols-2 content-center" : "grid-cols-1"}`}>
        {cams.map((c, i) => (
          <div
            key={`${c.name}#${nonce}`}
            className={`relative flex min-h-0 items-center justify-center overflow-hidden rounded-2xl border bg-neutral-900 ${muted ? "border-neutral-800/60" : "border-neutral-800"}`}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={c.url}
              alt={c.name || t("Live view from the world")}
              onLoad={onFirstLoad && i === 0 ? () => onFirstLoad(false) : undefined}
              onError={onFirstLoad && i === 0 ? () => onFirstLoad(true) : undefined}
              className={`max-h-full max-w-full rounded-xl transition-opacity ${disconnected ? "opacity-10" : muted ? "opacity-80" : "opacity-100"}`}
            />
            {c.name && (
              <span className="absolute left-2 top-2 rounded bg-neutral-950/70 px-1.5 py-0.5 font-mono text-[10px] text-neutral-300">
                {c.name}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
