"use client";
import { useState } from "react";
import { createSession, deleteSession, type Brain, type World, type SessionSummary } from "@/lib/api";

export default function SessionSidebar({
  sessions,
  worlds,
  brains,
  currentId,
  onSelect,
  onChanged,
}: {
  sessions: SessionSummary[];
  worlds: World[];
  brains: Brain[];
  currentId: string;
  onSelect: (id: string) => void;
  onChanged: (id?: string) => void;
}) {
  const [creating, setCreating] = useState(false);
  const [world, setWorld] = useState(""); // "" = 纯聊天
  const [brain, setBrain] = useState("");

  const firstAvailBrain = brains.find((b) => b.available)?.name ?? brains[0]?.name ?? "";

  function openForm() {
    setWorld(worlds[0]?.name ?? "");
    setBrain(firstAvailBrain);
    setCreating(true);
  }
  async function doCreate() {
    const created = await createSession(world || null, brain || firstAvailBrain);
    setCreating(false);
    onChanged(created.id);
  }
  async function doDelete(id: string) {
    if (!confirm("删除这个会话?(不可恢复)")) return;
    await deleteSession(id);
    onChanged(); // 不指定 id:父组件刷新后若当前会话已被删则自动重选(见 page.tsx)
  }

  const pill = (active: boolean, dim = false) =>
    `rounded-lg border px-2.5 py-1 text-xs ${
      active
        ? "border-blue-600 bg-blue-600 text-white"
        : "border-neutral-700 text-neutral-300 hover:border-neutral-500"
    } ${dim ? "opacity-50" : ""}`;

  return (
    <aside className="flex h-screen flex-col border-r border-neutral-800 bg-neutral-900">
      <div className="border-b border-neutral-800 p-3">
        <button onClick={openForm} className="w-full rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium">
          + 新建会话
        </button>
      </div>

      {creating && (
        <div className="space-y-3 border-b border-neutral-800 p-3 text-xs">
          <div>
            <div className="mb-1.5 text-neutral-400">连接哪个世界</div>
            <div className="flex flex-wrap gap-1.5">
              <button className={pill(world === "")} onClick={() => setWorld("")}>
                纯聊天
              </button>
              {worlds.map((w) => (
                <button key={w.name} className={pill(world === w.name, !w.online)} onClick={() => setWorld(w.name)}>
                  {w.name}
                  {w.online ? "" : "(离线)"}
                </button>
              ))}
            </div>
          </div>
          <div>
            <div className="mb-1.5 text-neutral-400">用哪个大脑</div>
            <div className="flex flex-wrap gap-1.5">
              {brains.map((b) => (
                <button
                  key={b.name}
                  className={pill(brain === b.name, !b.available)}
                  onClick={() => setBrain(b.name)}
                >
                  {b.label}
                  {b.available ? "" : "(未配置)"}
                </button>
              ))}
            </div>
          </div>
          <div className="flex gap-2 pt-1">
            <button onClick={doCreate} className="rounded-lg bg-blue-600 px-3 py-1.5">
              创建会话
            </button>
            <button onClick={() => setCreating(false)} className="rounded-lg bg-neutral-700 px-3 py-1.5">
              取消
            </button>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-2">
        {sessions.length === 0 && (
          <div className="p-3 text-xs text-neutral-500">还没有会话,点上面新建。</div>
        )}
        {sessions.map((s) => (
          <div
            key={s.id}
            className={`group mb-1 flex items-start rounded-lg ${
              s.id === currentId ? "bg-neutral-800" : "hover:bg-neutral-800/50"
            }`}
          >
            <button
              onClick={() => onSelect(s.id)}
              className="min-w-0 flex-1 rounded-lg p-2 text-left text-xs"
            >
              <div className="flex items-center justify-between">
                <span className="truncate font-medium">{s.title}</span>
                {s.status === "frozen" && (
                  <span className="ml-1 shrink-0 text-[10px] text-amber-500">🔒只读</span>
                )}
              </div>
              <div className="mt-0.5 text-[10px] text-neutral-500">
                {s.world ?? "纯聊天"} · {s.brain}
              </div>
            </button>
            <button
              onClick={() => doDelete(s.id)}
              title="删除会话"
              className="mr-1 mt-1 shrink-0 rounded px-1.5 py-1 text-[11px] text-neutral-600 opacity-0 hover:bg-neutral-700 hover:text-red-400 group-hover:opacity-100"
            >
              ✕
            </button>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-3 border-t border-neutral-800 p-3">
        <a href="/awi" className="text-xs text-blue-400 hover:underline">AWI 仪表盘 →</a>
        <a href="/anima-logs" className="text-xs text-blue-400 hover:underline">anima-logs →</a>
      </div>
    </aside>
  );
}
