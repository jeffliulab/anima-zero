"use client";
import { useEffect, useState } from "react";

// 中间传感区：嵌世界的实时画面(MJPEG)。
// 三种状态：
//   - 无世界(纯聊天)：提示"未连接世界"。
//   - 有世界但连不上(进程没起 / 中途挂了 / 收不到画面)：显示"未连接到世界…请检查"的断连提示 + 重试。
//   - 正常：显示实时画面。
// 断连判定：先用后端给的 online 作初值(秒级反馈)，再以 <img> 实际能否加载为准(连接被拒会触发 onError)。
export default function SensingArea({
  streamUrl,
  worldName,
  online,
}: {
  streamUrl: string | null;
  worldName: string | null;
  online: boolean | null; // null = 纯聊天/无世界
}) {
  const [failed, setFailed] = useState(false);
  const [nonce, setNonce] = useState(0); // 点"重试"时 +1，强制 <img> 重新连

  // 切换世界 / 点重试 / 后端在线状态变化 → 重置：以 online 作断连初值，之后交给 img 的 onLoad/onError 校正
  useEffect(() => {
    setFailed(online === false);
  }, [streamUrl, online, nonce]);

  const disconnected = !!worldName && !!streamUrl && failed;

  return (
    <section className="flex flex-col gap-3 p-6">
      <h2 className="text-sm font-medium text-neutral-400">
        传感区 · ANIMA 看到的画面{worldName ? `（${worldName} · 实时）` : ""}
      </h2>
      <div className="relative flex flex-1 items-center justify-center overflow-hidden rounded-2xl border border-neutral-800 bg-neutral-900">
        {!streamUrl ? (
          <span className="text-sm text-neutral-500">纯聊天 / 未连接世界</span>
        ) : (
          <>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              key={`${streamUrl}#${nonce}#${online}`}
              src={streamUrl}
              alt="世界实时画面"
              onLoad={() => setFailed(false)}
              onError={() => setFailed(true)}
              className={`max-h-full max-w-full rounded-xl transition-opacity ${disconnected ? "opacity-10" : "opacity-100"}`}
            />
            {disconnected && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-neutral-950/70 p-6 text-center">
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
