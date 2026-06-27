"use client";
import { useCallback, useEffect, useState } from "react";
import SessionSidebar from "@/components/SessionSidebar";
import SensingArea from "@/components/SensingArea";
import ChatPanel from "@/components/ChatPanel";
import {
  getBrains,
  getWorlds,
  listSessions,
  type Brain,
  type World,
  type SessionSummary,
} from "@/lib/api";

export default function Home() {
  const [brains, setBrains] = useState<Brain[]>([]);
  const [worlds, setWorlds] = useState<World[]>([]);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [currentId, setCurrentId] = useState("");

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

  const current = sessions.find((x) => x.id === currentId) || null;
  const worldUrl = current?.world ? worlds.find((w) => w.name === current.world)?.url ?? null : null;
  const streamUrl = worldUrl ? `${worldUrl}/stream` : null;

  return (
    <main className="grid h-screen grid-cols-[240px_1fr_440px] bg-neutral-950 text-neutral-100">
      <SessionSidebar
        sessions={sessions}
        worlds={worlds}
        brains={brains}
        currentId={currentId}
        onSelect={setCurrentId}
        onChanged={async (id) => {
          await refreshSessions();
          if (id) setCurrentId(id);
        }}
      />
      <SensingArea streamUrl={streamUrl} worldName={current?.world ?? null} />
      <ChatPanel session={current} brains={brains} onSessionsChanged={refreshSessions} />
    </main>
  );
}
