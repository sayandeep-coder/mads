"use client";

import { useEffect, useState } from "react";
import type { GeneratedFile } from "@/lib/types";

const API_BASE =
  typeof window !== "undefined"
    ? `${window.location.protocol}//${window.location.hostname}:8000`
    : "";

const KIND_LABEL: Record<GeneratedFile["kind"], string> = {
  pdf: "PDF",
  pptx: "Slides",
  xlsx: "Spreadsheet",
  image: "Image",
  file: "File",
};

// Kinds the in-app split-pane preview (PreviewPane) actually knows how to
// render — everything else still falls back to the chip's original
// share/download-only behavior, same as before this feature existed.
const PREVIEWABLE_KINDS: ReadonlySet<GeneratedFile["kind"]> = new Set(["pdf", "xlsx"]);

function fileUrl(file: GeneratedFile): string {
  return `${API_BASE}/api/files?path=${encodeURIComponent(file.path)}`;
}

/**
 * iOS Safari only shows the actual share sheet for navigator.share() calls
 * made synchronously within the click handler — once an `await fetch(...)`
 * happens first, Safari decides the user gesture has "expired" and just
 * opens the file directly instead of presenting the sheet (exactly the bug
 * this button used to have). The fix is to fetch the file *before* the tap
 * (on mount, via useEffect below) so share() can fire with zero awaits
 * ahead of it inside the click handler.
 */
export function DownloadChip({
  file,
  onOpen,
}: {
  file: GeneratedFile;
  onOpen?: (file: GeneratedFile) => void;
}) {
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [preparedFile, setPreparedFile] = useState<File | null>(null);
  const canPreview = PREVIEWABLE_KINDS.has(file.kind) && Boolean(onOpen);

  // Prefetch as soon as the chip appears — a chip only renders once the
  // file already exists server-side, so there's nothing to wait for. This
  // is what makes the later navigator.share() call in handleShareOrDownload
  // able to fire synchronously within the click, which iOS requires to
  // show the actual share sheet instead of just opening the file.
  useEffect(() => {
    let cancelled = false;
    fetch(fileUrl(file))
      .then((res) => {
        if (!res.ok) throw new Error(`Server responded ${res.status}`);
        return res.blob();
      })
      .then((blob) => {
        if (!cancelled) setPreparedFile(new File([blob], file.name, { type: blob.type }));
      })
      .catch(() => {
        // Silent — handleShareOrDownload falls back to fetching on tap if this failed.
      });
    return () => {
      cancelled = true;
    };
  }, [file]);

  const handleShareOrDownload = () => {
    if (!preparedFile) {
      // Prefetch hasn't finished yet (slow network, or tapped instantly)
      // — fall back to a plain download. This still works, it just won't
      // be the share sheet, since we can't await a fetch inside this
      // gesture on iOS.
      setStatus("loading");
      fetch(fileUrl(file))
        .then((res) => {
          if (!res.ok) throw new Error(`Server responded ${res.status}`);
          return res.blob();
        })
        .then((blob) => {
          const blobUrl = URL.createObjectURL(blob);
          const link = document.createElement("a");
          link.href = blobUrl;
          link.download = file.name;
          document.body.appendChild(link);
          link.click();
          link.remove();
          URL.revokeObjectURL(blobUrl);
          setStatus("idle");
        })
        .catch(() => setStatus("error"));
      return;
    }

    const canShareFile =
      typeof navigator !== "undefined" &&
      "share" in navigator &&
      "canShare" in navigator &&
      navigator.canShare({ files: [preparedFile] });

    if (canShareFile) {
      navigator.share({ files: [preparedFile] }).catch((err) => {
        // AbortError means the user dismissed the share sheet — not a failure.
        if ((err as Error).name !== "AbortError") setStatus("error");
      });
      return;
    }

    // Desktop / unsupported browsers: trigger a normal browser download.
    const blobUrl = URL.createObjectURL(preparedFile);
    const link = document.createElement("a");
    link.href = blobUrl;
    link.download = file.name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(blobUrl);
  };

  const handleChipTap = () => {
    if (canPreview) {
      onOpen!(file);
      return;
    }
    handleShareOrDownload();
  };

  return (
    <div
      className="flex items-center gap-2.5 rounded-xl border border-border bg-surface px-3 py-2.5 text-left text-[13px] transition-colors hover:border-border-strong"
    >
      <button
        type="button"
        onClick={handleChipTap}
        disabled={status === "loading"}
        className="flex min-w-0 flex-1 items-center gap-2.5 disabled:opacity-60"
      >
        <FileIcon kind={file.kind} />
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="truncate font-medium text-text">{file.name}</span>
          <span className="text-text-muted">
            {status === "loading"
              ? "Preparing…"
              : status === "error"
                ? "Couldn't open — tap to retry"
                : canPreview
                  ? `${KIND_LABEL[file.kind]} · tap to open`
                  : KIND_LABEL[file.kind]}
          </span>
        </span>
      </button>

      <button
        type="button"
        onClick={handleShareOrDownload}
        disabled={status === "loading"}
        aria-label="Share or download"
        title="Share or download"
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-text-muted transition-colors hover:bg-code-bg hover:text-text disabled:opacity-60"
      >
        <ShareIcon />
      </button>
    </div>
  );
}

function FileIcon({ kind }: { kind: GeneratedFile["kind"] }) {
  return (
    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-code-bg text-text-muted">
      <svg viewBox="0 0 20 20" width="17" height="17" fill="none">
        <path
          d="M6 2.5h5.5L15.5 6.5V16a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1Z"
          stroke="currentColor"
          strokeWidth="1.4"
          strokeLinejoin="round"
        />
        <path d="M11.25 2.5V6a.75.75 0 0 0 .75.75h3.5" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
      </svg>
      <span className="sr-only">{kind}</span>
    </span>
  );
}

function ShareIcon() {
  return (
    <svg viewBox="0 0 20 20" width="16" height="16" fill="none" className="shrink-0">
      <path
        d="M10 3v9M10 3l-3 3M10 3l3 3M4.5 10v5a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1v-5"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
