"use client";
import { useCallback, useEffect, useState } from "react";
import SessionSidebar from "@/components/SessionSidebar";
import SensingArea from "@/components/SensingArea";
import ChatPanel from "@/components/ChatPanel";
import ChessModePanel from "@/components/ChessModePanel";
import AwiDashboard from "@/components/AwiDashboard";
import AnimaLogsView from "@/components/AnimaLogsView";
import {
  getBrains,
  getWorlds,
  getGame,
  listSessions,
  POLL_GAME_STATE_MS,
  POLL_AWI_MS,
  type Brain,
  type World,
  type SessionSummary,
} from "@/lib/api";

export default function Home() {
  const [brains, setBrains] = useState<Brain[]>([]);
  const [worlds, setWorlds] = useState<World[]>([]);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [currentId, setCurrentId] = useState("");
  const [gameActive, setGameActive] = useState(false);
  // 中间区当前看什么：会话视图(默认) / 留白主页 / 内嵌 AWI / 内嵌 anima-logs
  const [view, setView] = useState<"session" | "home" | "awi" | "logs">("session");

  // 轮询当前会话是否在 Chess Mode（对弈行为树跑着）→ 决定是否浮现面板
  useEffect(() => {
    if (!currentId) {
      setGameActive(false);
      return;
    }
    let stop = false;
    const tick = async () => {
      const g = await getGame(currentId).catch(() => null);
      if (!stop) setGameActive(!!g?.active);
    };
    tick();
    const t = setInterval(tick, POLL_GAME_STATE_MS);
    return () => {
      stop = true;
      clearInterval(t);
    };
  }, [currentId]);

  const refreshSessions = useCallback(async () => {
    const s = await listSessions().catch(() => []);
    setSessions(s);
    return s;
  }, []);

  useEffect(() => {
    (async () => {
      setBrains(await getBrains().catch(() => []));
      setWorlds(await getWorlds().catch(() => []));
      const s = await refreshSessions();
      if (s.length) setCurrentId((id) => id || s[0].id);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 周期性刷新世界在线状态：让"未连接世界"提示和侧栏的"(离线)"保持实时（世界中途挂了也能反映）
  useEffect(() => {
    const t = setInterval(() => {
      getWorlds().then(setWorlds).catch(() => {});
    }, POLL_AWI_MS);
    return () => clearInterval(t);
  }, []);

  const current = sessions.find((x) => x.id === currentId) || null;
  const currentWorld = current?.world ? worlds.find((w) => w.name === current.world) ?? null : null;
  const worldUrl = currentWorld?.url ?? null;
  const streamUrl = worldUrl ? `${worldUrl}/stream` : null;
  // 该会话所连世界在不在线：null = 纯聊天/无世界；true/false = 在线/离线
  const worldOnline = current?.world ? currentWorld?.online ?? false : null;

  const inSession = view === "session";

  return (
    <main className="grid h-screen grid-cols-[240px_minmax(0,1fr)_440px] bg-neutral-950 text-neutral-100">
      <SessionSidebar
        sessions={sessions}
        worlds={worlds}
        brains={brains}
        currentId={currentId}
        onSelect={(id) => {
          setCurrentId(id);
          setView("session"); // 点 session = 回到该会话的正常视图
        }}
        onChanged={async (id) => {
          const s = await refreshSessions();
          if (id) setCurrentId(id);
          // 没指定 id(如删除后):当前会话还在就保持,否则重选第一个(没有则清空)
          else setCurrentId((cur) => (s.find((x) => x.id === cur) ? cur : s[0]?.id ?? ""));
        }}
        onHome={() => setView("home")}
        onOpenPanel={(p) => setView(p)}
      />

      {/* 中间区：按 view 切换。子页(awi/logs)仅在选中时挂载，切走即卸载、停轮询。 */}
      {view === "awi" ? (
        <AwiDashboard embedded onOpenLogs={() => setView("logs")} />
      ) : view === "logs" ? (
        <AnimaLogsView embedded sessionId={currentId} />
      ) : view === "home" ? (
        <div className="flex min-w-0 items-center justify-center overflow-hidden bg-neutral-950 p-8 text-center text-sm text-neutral-600">
          ANIMA · 在左侧选择或新建一个会话开始；左下角可查看 AWI 仪表盘 / anima-logs。
        </div>
      ) : (
        <SensingArea streamUrl={streamUrl} worldName={current?.world ?? null} online={worldOnline} />
      )}

      {/* 右栏：session 视图维持原逻辑(对局→下棋面板，否则聊天)；其它 view → 全新空会话且只读(paused)，
          不显示别的 session 记录（将来 AWI/logs 各自的 chatbot 在此长出来）。 */}
      {inSession && gameActive && currentId ? (
        <ChessModePanel
          sessionId={currentId}
          streamUrl={streamUrl}
          onExit={() => setGameActive(false)}
        />
      ) : (
        <ChatPanel
          session={inSession ? current : null}
          brains={brains}
          onSessionsChanged={refreshSessions}
          paused={!inSession}
        />
      )}
    </main>
  );
}
