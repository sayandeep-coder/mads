"use client";

import { useEffect, useRef, useState } from "react";
import type { ToolCallState } from "@/lib/types";

const STATUS_LABEL: Record<ToolCallState["status"], string> = {
  running: "Using",
  done: "Used",
  error: "Failed",
};

const TERMINAL_STATUS_LABEL: Record<ToolCallState["status"], string> = {
  running: "Running",
  done: "Ran",
  error: "Failed",
};

/** Turns "search_memory" into "Search memory" for display. */
function humanizeToolName(name: string): string {
  const words = name.split("_").join(" ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function ToolCallRow({ call }: { call: ToolCallState }) {
  const isTerminal = call.name === "run_command";
  const filePath = typeof call.args?.path === "string" ? call.args.path : undefined;
  const fileContent = typeof call.args?.content === "string" ? call.args.content : undefined;
  const isFileWrite = call.name === "write_file" && filePath !== undefined && fileContent !== undefined;
  const [expanded, setExpanded] = useState(isTerminal || isFileWrite);
  const hasArgs = call.args && Object.keys(call.args).length > 0;
  const command = typeof call.args?.command === "string" ? call.args.command : undefined;

  if (isTerminal) {
    return <TerminalCallRow call={call} command={command} expanded={expanded} onToggle={() => setExpanded((e) => !e)} />;
  }

  if (isFileWrite) {
    return (
      <FileWriteCallRow call={call} path={filePath} content={fileContent} expanded={expanded} onToggle={() => setExpanded((e) => !e)} />
    );
  }

  return (
    <div className="flex flex-col">
      <button
        type="button"
        onClick={() => hasArgs && setExpanded((e) => !e)}
        className={`group flex items-center gap-2 text-[13px] text-text-muted transition-colors ${
          hasArgs ? "cursor-pointer hover:text-text" : "cursor-default"
        }`}
        aria-expanded={hasArgs ? expanded : undefined}
      >
        <ToolStatusIcon status={call.status} />
        <span>
          {STATUS_LABEL[call.status]}{" "}
          <span className="font-medium text-text">{humanizeToolName(call.name)}</span>
        </span>
        {hasArgs && (
          <svg
            viewBox="0 0 16 16"
            width="12"
            height="12"
            className={`ml-0.5 text-text-faint transition-transform ${expanded ? "rotate-180" : ""}`}
            fill="none"
          >
            <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        )}
      </button>

      {expanded && hasArgs && (
        <pre className="mt-1 max-w-full overflow-x-auto rounded-md bg-code-bg px-3 py-2 font-mono text-[12px] leading-relaxed text-text-muted">
          {JSON.stringify(call.args, null, 2)}
        </pre>
      )}
    </div>
  );
}

/** Claude-Code-style live terminal block for a run_command call — grows as
 * stdout/stderr chunks arrive, auto-scrolls to the bottom, and shows a
 * blinking cursor while the command is still running. */
function TerminalCallRow({
  call,
  command,
  expanded,
  onToggle,
}: {
  call: ToolCallState;
  command: string | undefined;
  expanded: boolean;
  onToggle: () => void;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [call.terminalOutput]);

  return (
    <div className="flex flex-col">
      <button
        type="button"
        onClick={onToggle}
        className="group flex items-center gap-2 text-[13px] text-text-muted transition-colors hover:text-text"
        aria-expanded={expanded}
      >
        <ToolStatusIcon status={call.status} />
        <span>
          {TERMINAL_STATUS_LABEL[call.status]} <span className="font-medium text-text">terminal</span>
        </span>
        <svg
          viewBox="0 0 16 16"
          width="12"
          height="12"
          className={`ml-0.5 text-text-faint transition-transform ${expanded ? "rotate-180" : ""}`}
          fill="none"
        >
          <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {expanded && (
        <div className="mt-1.5 overflow-hidden rounded-lg border border-border bg-[#0b0c0d]">
          {command && (
            <div className="flex items-center gap-2 border-b border-white/10 px-3 py-1.5">
              <span className="h-2 w-2 shrink-0 rounded-full bg-[#ff5f57]" />
              <span className="h-2 w-2 shrink-0 rounded-full bg-[#febc2e]" />
              <span className="h-2 w-2 shrink-0 rounded-full bg-[#28c840]" />
              <code className="ml-1.5 truncate font-mono text-[11px] text-white/50">{command}</code>
            </div>
          )}
          <div ref={scrollRef} className="max-h-60 overflow-y-auto px-3 py-2">
            <pre className="whitespace-pre-wrap break-all font-mono text-[12px] leading-relaxed text-[#d4d4d4]">
              {call.terminalOutput || (call.status === "running" ? "" : "(no output)")}
              {call.status === "running" && <span className="typing-caret text-[#d4d4d4]" aria-hidden="true" />}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}

/** Shows a written file's full content immediately, expanded by default,
 * instead of a collapsed generic args dump — the content itself can't
 * stream character-by-character the way run_command's output does (a
 * single MCP tool call only ever returns once, with no partial-result
 * protocol), but at least it's visible right away rather than hidden
 * behind a click. */
function FileWriteCallRow({
  call,
  path,
  content,
  expanded,
  onToggle,
}: {
  call: ToolCallState;
  path: string;
  content: string;
  expanded: boolean;
  onToggle: () => void;
}) {
  const fileName = path.split("/").pop() || path;

  return (
    <div className="flex flex-col">
      <button
        type="button"
        onClick={onToggle}
        className="group flex items-center gap-2 text-[13px] text-text-muted transition-colors hover:text-text"
        aria-expanded={expanded}
      >
        <ToolStatusIcon status={call.status} />
        <span className="min-w-0 truncate">
          {STATUS_LABEL[call.status]} <span className="font-medium text-text">{fileName}</span>
        </span>
        <svg
          viewBox="0 0 16 16"
          width="12"
          height="12"
          className={`ml-0.5 shrink-0 text-text-faint transition-transform ${expanded ? "rotate-180" : ""}`}
          fill="none"
        >
          <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {expanded && (
        <div className="mt-1.5 overflow-hidden rounded-lg border border-border bg-[#0b0c0d]">
          <div className="flex items-center gap-2 border-b border-white/10 px-3 py-1.5">
            <code className="truncate font-mono text-[11px] text-white/50">{path}</code>
          </div>
          <div className="max-h-72 overflow-y-auto px-3 py-2">
            <pre className="whitespace-pre-wrap break-all font-mono text-[12px] leading-relaxed text-[#d4d4d4]">{content}</pre>
          </div>
        </div>
      )}
    </div>
  );
}

function ToolStatusIcon({ status }: { status: ToolCallState["status"] }) {
  if (status === "running") {
    return (
      <svg viewBox="0 0 16 16" width="13" height="13" className="animate-spin text-accent" fill="none">
        <circle cx="8" cy="8" r="6" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2" />
        <path d="M14 8a6 6 0 0 0-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
    );
  }
  if (status === "error") {
    return (
      <svg viewBox="0 0 16 16" width="13" height="13" fill="none" className="text-danger">
        <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.5" />
        <path d="M8 5v4M8 11h.01" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 16 16" width="13" height="13" fill="none" className="text-text-muted">
      <path
        d="M4 8.5l2.5 2.5L12 5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
