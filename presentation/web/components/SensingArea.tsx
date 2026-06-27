"use client";

// 直接嵌世界的实时视频流(MJPEG):世界自己推流,这边只负责显示。
// 摄像头 / MuJoCo 以后也走这条路——换个世界,它的 /stream 给摄像头帧 / 渲染帧即可。
export default function SensingArea({
  streamUrl,
  worldName,
}: {
  streamUrl: string | null;
  worldName: string | null;
}) {
  return (
    <section className="flex flex-col gap-3 p-6">
      <h2 className="text-sm font-medium text-neutral-400">
        传感区 · ANIMA 看到的画面{worldName ? `（${worldName} · 实时）` : ""}
      </h2>
      <div className="flex flex-1 items-center justify-center rounded-2xl border border-neutral-800 bg-neutral-900">
        {streamUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={streamUrl} alt="世界实时画面" className="max-h-full max-w-full rounded-xl" />
        ) : (
          <span className="text-sm text-neutral-500">纯聊天 / 未连接世界</span>
        )}
      </div>
    </section>
  );
}
