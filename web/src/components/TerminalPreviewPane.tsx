"use client";

import { useEffect, useRef, useState } from "react";
import { useCodeRun } from "@/lib/useCodeRun";
import type { CodeRunTarget } from "@/lib/types";

/** The split-pane's live, interactive terminal — opened by the "Run" button
 * on a code block in a chat message. Unlike the agent's own run_command
 * (which only streams output outward), this is full-duplex: the user can
 * type into a running program's stdin, same as a real terminal. */
export function TerminalPreviewPane({ target, onClose }: { target: CodeRunTarget; onClose: () => void }) {
  const { output, status, exitCode, errorMessage, start, sendInput, stop } = useCodeRun();
  const [inputValue, setInputValue] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // No "already started" ref guard here — React 18 Strict Mode (on by
  // default in Next.js dev) deliberately double-invokes effects
  // (mount -> cleanup -> mount again) specifically to catch effects that
  // don't tolerate being re-run. useCodeRun's own cleanup closes the
  // socket on that fake unmount; a guard that blocked the second `start()`
  // call left the connection closed with nothing to replace it — which is
  // exactly the "Error" status with no output this was producing. Calling
  // `start` on every dependency change is correct and safe: `start` itself
  // closes any previous socket first, and target.id/language/code only
  // actually change when a new Run is clicked, not on unrelated re-renders.
  useEffect(() => {
    start(target.language, target.code);
  }, [target.id, target.language, target.code, start]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [output]);

  useEffect(() => {
    if (status === "running") inputRef.current?.focus();
  }, [status]);

  const submitInput = () => {
    if (status !== "running") return;
    sendInput(inputValue);
    setInputValue("");
  };

  return (
    <div className="flex h-full flex-col bg-surface">
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <TerminalIcon />
          <span className="truncate text-[14px] font-medium text-text">Terminal — {target.language}</span>
          <StatusPill status={status} exitCode={exitCode} />
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {status === "running" && (
            <button
              type="button"
              onClick={stop}
              className="flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-[12.5px] font-medium text-danger transition-colors hover:bg-danger/10"
              aria-label="Stop run"
              title="Stop"
            >
              <StopIcon />
              Stop
            </button>
          )}
          <button
            type="button"
            onClick={() => {
              stop();
              onClose();
            }}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-text-muted transition-colors hover:bg-code-bg hover:text-text"
            aria-label="Close terminal"
            title="Close"
          >
            <CloseIcon />
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col bg-[#0b0c0d]">
        <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
          <pre className="whitespace-pre-wrap break-all font-mono text-[13px] leading-relaxed text-[#d4d4d4]">
            {output}
            {status === "running" && <span className="typing-caret text-[#d4d4d4]" aria-hidden="true" />}
          </pre>
          {errorMessage && <p className="mt-2 text-[13px] text-danger">{errorMessage}</p>}
        </div>

        <div className="flex shrink-0 items-center gap-2 border-t border-white/10 px-3 py-2">
          <span className="font-mono text-[13px] text-[#6a9955]">{">"}</span>
          <input
            ref={inputRef}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submitInput();
            }}
            disabled={status !== "running"}
            placeholder={status === "running" ? "Type input and press Enter…" : "Program finished"}
            autoComplete="off"
            autoCorrect="off"
            spellCheck={false}
            className="w-full bg-transparent font-mono text-[13px] text-[#d4d4d4] placeholder:text-white/30 focus:outline-none disabled:cursor-not-allowed"
          />
        </div>
      </div>
    </div>
  );
}

function StatusPill({ status, exitCode }: { status: string; exitCode: number | null }) {
  if (status === "running") {
    return (
      <span className="flex items-center gap-1.5 rounded-full bg-accent/15 px-2 py-0.5 text-[11px] font-medium text-accent">
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
        Running
      </span>
    );
  }
  if (status === "exited") {
    const ok = exitCode === 0;
    return (
      <span
        className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
          ok ? "bg-accent/15 text-accent" : "bg-danger/15 text-danger"
        }`}
      >
        Exited ({exitCode})
      </span>
    );
  }
  if (status === "error") {
    return <span className="rounded-full bg-danger/15 px-2 py-0.5 text-[11px] font-medium text-danger">Error</span>;
  }
  return null;
}

function TerminalIcon() {
  return (
    <svg viewBox="0 0 20 20" width="16" height="16" fill="none" className="shrink-0 text-text-muted">
      <rect x="2.5" y="3.5" width="15" height="13" rx="1.6" stroke="currentColor" strokeWidth="1.4" />
      <path d="M6 8l2.5 2-2.5 2M10.5 12h3.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function StopIcon() {
  return (
    <svg viewBox="0 0 16 16" width="12" height="12" fill="none">
      <rect x="3" y="3" width="10" height="10" rx="1.5" fill="currentColor" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" fill="none">
      <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}
