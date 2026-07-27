"use client";
import { useState } from "react";

import { useI18n } from "@/lib/i18n";
import { approveWorld, getWorldManifest, type TrustState, type WorldManifest } from "@/lib/api";

/**
 * Approving a world, in the browser.
 *
 * A world's guidance is concatenated into the brain's system prompt and its tool
 * descriptions go into the model's tool sheet — all of it written by whoever runs that URL.
 * So none of it reaches the brain until a person has looked at it and said yes.
 *
 * The design rule here is one thing: **show the whole text, not a summary.** An approval
 * dialog that displays an abridged version approves something that was never read, which
 * is worse than having no dialog at all — it manufactures the feeling of having checked.
 *
 * 在浏览器里批准一个世界。
 *
 * 世界的说明书会被拼进大脑的系统提示词、它的工具描述会进模型的工具单——而这些全都由运行那个 URL
 * 的人书写。所以在有人亲眼看过并点头之前，它们一样都不会到达大脑。
 *
 * 这里的设计规矩只有一条：**把全文摊出来，不给摘要。** 一个显示删节版的审批对话框，批准的是一个
 * 从没被读过的东西——那比没有对话框更糟，因为它**制造了"我检查过了"的错觉**。
 */
export function WorldTrust({ name, state, onApproved }: {
  name: string;
  state: TrustState;
  onApproved?: () => void;
}) {
  const { t } = useI18n();
  const [manifest, setManifest] = useState<WorldManifest | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");

  if (state === "trusted" || state === "") return null;

  const changed = state === "changed";

  async function open() {
    setBusy(true);
    setManifest(await getWorldManifest(name));
    setBusy(false);
  }

  async function approve() {
    setBusy(true);
    const r = await approveWorld(name);
    setBusy(false);
    setNote(r.message);
    if (r.ok) {
      setManifest(null);
      onApproved?.();
    }
  }

  return (
    <div className="mt-3 rounded-lg border border-amber-700/60 bg-amber-950/30 p-3">
      <div className="text-sm font-medium text-amber-300">
        {changed
          ? t("⚠ 这个世界和你上次批准时不一样了")
          : t("⚠ 这个世界还没有被批准")}
      </div>
      <p className="mt-1 text-xs leading-relaxed text-neutral-400">
        {changed
          ? t("它的能力清单变了。改动内容在下面；确认无误再重新批准。")
          : t("在你批准之前，它的工具和说明书不会进入大脑——所以现在它列得出来，但驱动不了。")}
      </p>

      {manifest === null ? (
        <button onClick={open} disabled={busy}
          className="mt-2 rounded border border-amber-600 px-2 py-1 text-xs text-amber-200 hover:bg-amber-900/40 disabled:opacity-50">
          {busy ? t("读取中…") : t("看看它声明了什么")}
        </button>
      ) : (
        <div className="mt-3 space-y-3">
          {!manifest.ok && <div className="text-xs text-red-400">{manifest.message}</div>}

          {manifest.changes.length > 0 && (
            <div>
              <div className="text-xs font-medium text-amber-300">{t("变了什么")}</div>
              <ul className="mt-1 space-y-0.5">
                {manifest.changes.map((c, i) => (
                  <li key={i} className="text-xs text-neutral-300">· {c}</li>
                ))}
              </ul>
            </div>
          )}

          <div>
            <div className="text-xs font-medium text-neutral-300">
              {t("它声明的动作")}（{manifest.tools.length}）
            </div>
            <div className="mt-1 space-y-2">
              {manifest.tools.map((tool) => (
                <div key={tool.name} className="rounded border border-neutral-800 bg-neutral-950 p-2">
                  <div className="text-xs">
                    <span className="font-mono text-neutral-200">{tool.name}</span>{" "}
                    <span className={tool.kind === "read" || tool.kind === "judge"
                      ? "text-neutral-500" : "text-amber-400"}>
                      [{tool.kind}] {tool.kind === "read" || tool.kind === "judge"
                        ? t("只读") : t("会改变世界")}
                    </span>
                  </div>
                  {/* 描述原样显示、不截断：它会原样进模型的工具单，那就该原样给人看。 */}
                  <p className="mt-1 whitespace-pre-wrap text-[11px] leading-relaxed text-neutral-400">
                    {tool.description || t("(没有描述)")}
                  </p>
                </div>
              ))}
            </div>
          </div>

          <div>
            <div className="text-xs font-medium text-neutral-300">
              {t("它的说明书")}（{t("会被拼进大脑的系统提示词")}，{manifest.guidance.length} {t("字")}）
            </div>
            {/* 全文，不折叠、不摘要——见本文件顶部的说明。 */}
            <pre className="mt-1 max-h-64 overflow-auto whitespace-pre-wrap rounded border border-neutral-800 bg-neutral-950 p-2 text-[11px] leading-relaxed text-neutral-400">
              {manifest.guidance || t("(没有说明书)")}
            </pre>
          </div>

          <div className="flex items-center gap-2">
            <button onClick={approve} disabled={busy || !manifest.ok}
              className="rounded bg-amber-700 px-3 py-1 text-xs text-white hover:bg-amber-600 disabled:opacity-50">
              {busy ? t("处理中…") : changed ? t("我看过了，重新批准") : t("我看过了，批准它")}
            </button>
            <button onClick={() => setManifest(null)} disabled={busy}
              className="rounded border border-neutral-700 px-2 py-1 text-xs text-neutral-400 hover:bg-neutral-800">
              {t("收起")}
            </button>
            <span className="text-[11px] text-neutral-500">
              {t("只批准你信任的世界")}
            </span>
          </div>
        </div>
      )}

      {note && <div className="mt-2 text-xs text-green-400">{note}</div>}
    </div>
  );
}
