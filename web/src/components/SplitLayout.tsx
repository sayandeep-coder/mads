"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

const STORAGE_KEY = "mads_preview_split_pct";
const MIN_PCT = 24;
const MAX_PCT = 76;
const DEFAULT_PCT = 55; // chat gets 45%, preview gets 55% by default — mirrors Claude's artifact panel taking the larger share

/**
 * Chat on the left, a resizable preview panel on the right — same idea as
 * Claude's artifact split view. The divider drag updates a percentage
 * (not a pixel width) so the split holds its ratio across window resizes,
 * and that percentage is remembered in localStorage so reopening a
 * preview later keeps whatever ratio was last set (e.g. "30/70").
 */
export function SplitLayout({ left, right }: { left: ReactNode; right: ReactNode | null }) {
  const [splitPct, setSplitPct] = useState(DEFAULT_PCT);
  const containerRef = useRef<HTMLDivElement>(null);
  const draggingRef = useRef(false);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = Number(saved);
        if (Number.isFinite(parsed) && parsed >= MIN_PCT && parsed <= MAX_PCT) setSplitPct(parsed);
      }
    } catch {
      // localStorage can throw in a private/locked-down context — the
      // default split is a perfectly fine fallback, not worth surfacing.
    }
  }, []);

  const persist = useCallback((pct: number) => {
    try {
      localStorage.setItem(STORAGE_KEY, String(Math.round(pct)));
    } catch {
      // Same as above — a failed write just means the ratio isn't remembered.
    }
  }, []);

  const handlePointerMove = useCallback((event: PointerEvent) => {
    if (!draggingRef.current || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const pct = ((rect.right - event.clientX) / rect.width) * 100;
    setSplitPct(Math.min(MAX_PCT, Math.max(MIN_PCT, pct)));
  }, []);

  const stopDragging = useCallback(() => {
    if (!draggingRef.current) return;
    draggingRef.current = false;
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
    setSplitPct((current) => {
      persist(current);
      return current;
    });
  }, [persist]);

  useEffect(() => {
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", stopDragging);
    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", stopDragging);
    };
  }, [handlePointerMove, stopDragging]);

  const startDragging = (event: React.PointerEvent) => {
    event.preventDefault();
    draggingRef.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  };

  if (!right) return <div className="h-full w-full">{left}</div>;

  return (
    <div ref={containerRef} className="flex h-full w-full min-w-0">
      <div className="h-full min-w-0 flex-1 overflow-hidden">{left}</div>

      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize preview panel"
        onPointerDown={startDragging}
        className="group relative w-px shrink-0 cursor-col-resize bg-border"
      >
        <div className="absolute inset-y-0 -left-1.5 -right-1.5 group-hover:bg-accent/10" />
        <div className="absolute left-1/2 top-1/2 h-10 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full bg-border-strong opacity-0 transition-opacity group-hover:opacity-100" />
      </div>

      <div
        className="h-full min-w-0 shrink-0 overflow-hidden border-l border-border"
        style={{ width: `${splitPct}%` }}
      >
        {right}
      </div>
    </div>
  );
}
