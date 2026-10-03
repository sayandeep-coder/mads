"use client";

import { useCallback, useEffect, useState } from "react";
import { API_BASE } from "./useChat";
import type { ChatSession } from "./types";

/** Sidebar's session list — backed by the server's SQLite ChatStore
 * (server/store.py), so it survives restarts and isn't just a per-tab
 * localStorage cache. */
export function useSessions() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/sessions`);
      if (!res.ok) throw new Error();
      const data = (await res.json()) as { sessions: ChatSession[] };
      setSessions(data.sessions);
    } catch {
      // Leave whatever list we already had — a transient fetch failure
      // shouldn't blank out the sidebar.
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const rename = useCallback(async (id: string, title: string) => {
    setSessions((prev) => prev.map((s) => (s.id === id ? { ...s, title } : s)));
    try {
      await fetch(`${API_BASE}/api/sessions/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      });
    } catch {
      // Best-effort — a failed rename just reverts on the next refresh().
    }
  }, []);

  const remove = useCallback(async (id: string) => {
    setSessions((prev) => prev.filter((s) => s.id !== id));
    try {
      await fetch(`${API_BASE}/api/sessions/${id}`, { method: "DELETE" });
    } catch {
      // Best-effort — same as rename above.
    }
  }, []);

  return { sessions, loaded, refresh, rename, remove };
}
