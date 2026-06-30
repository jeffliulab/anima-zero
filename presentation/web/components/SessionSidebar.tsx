"use client";
import { useState } from "react";
import { createSession, deleteSession, type Brain, type World, type SessionSummary } from "@/lib/api";
import ThemeToggle from "./ThemeToggle";

export default function SessionSidebar({
  sessions,
  worlds,
  brains,
  currentId,
  onSelect,
  onChanged,
  onHome,
  onOpenPanel,
}: {
  sessions: SessionSummary[];
  worlds: World[];
  brains: Brain[];
  currentId: string;
  onSelect: (id: string) => void;
  onChanged: (id?: string) => void;
  onHome: () => void;                          // 点 🏠 主页 → 主页留白视图
  onOpenPanel: (p: "awi" | "logs") => void;    // 点底栏导航 → 在主界面中间内嵌该子页
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
      <button
        onClick={onHome}
        title="回到主页（留白）"
        className="flex items-center gap-2 border-b border-neutral-800 px-3 py-2.5 text-sm font-semibold text-neutral-200 transition-colors hover:bg-neutral-800"
      >
        <HomeIcon />
        <span>ANIMA</span>
        <span className="ml-auto text-[11px] font-normal text-neutral-500">主页</span>
      </button>
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

      <div className="space-y-0.5 border-t border-neutral-800 p-2">
        <button
          onClick={() => onOpenPanel("awi")}
          className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs text-neutral-300 transition-colors hover:bg-neutral-800 hover:text-neutral-100"
        >
          <DashboardIcon />
          <span>AWI 仪表盘</span>
          <span className="ml-auto text-neutral-600">›</span>
        </button>
        <button
          onClick={() => onOpenPanel("logs")}
          className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs text-neutral-300 transition-colors hover:bg-neutral-800 hover:text-neutral-100"
        >
          <LogsIcon />
          <span>anima-logs</span>
          <span className="ml-auto text-neutral-600">›</span>
        </button>
        <div className="mt-1 flex items-center gap-2 border-t border-neutral-800 px-2 pt-2 text-xs text-neutral-500">
          <span>外观</span>
          <span className="ml-auto">
            <ThemeToggle />
          </span>
        </div>
      </div>
    </aside>
  );
}

// 顶部主页图标
function HomeIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 10.5 12 3l9 7.5" />
      <path d="M5 9.5V20h14V9.5" />
    </svg>
  );
}

// 底栏导航小图标（描边风格与 ThemeToggle 一致，随主题变色）
function DashboardIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="3" width="7" height="9" rx="1" />
      <rect x="14" y="3" width="7" height="5" rx="1" />
      <rect x="14" y="12" width="7" height="9" rx="1" />
      <rect x="3" y="16" width="7" height="5" rx="1" />
    </svg>
  );
}

function LogsIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 6h16M4 12h16M4 18h10" />
    </svg>
  );
}
