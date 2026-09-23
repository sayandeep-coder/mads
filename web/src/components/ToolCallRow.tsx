"use client";

import { useState } from "react";
import type { ToolCallState } from "@/lib/types";

const STATUS_LABEL: Record<ToolCallState["status"], string> = {
  running: "Using",
  done: "Used",
  error: "Failed",
};

/** Turns "search_memory" into "Search memory" for display. */
function humanizeToolName(name: string): string {
  const words = name.split("_").join(" ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function ToolCallRow({ call }: { call: ToolCallState }) {
  const [expanded, setExpanded] = useState(false);
  const hasArgs = call.args && Object.keys(call.args).length > 0;

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
