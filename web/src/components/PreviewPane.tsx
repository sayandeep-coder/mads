"use client";

import { useEffect, useState } from "react";
import type { GeneratedFile } from "@/lib/types";

const API_BASE =
  typeof window !== "undefined"
    ? `${window.location.protocol}//${window.location.hostname}:8000`
    : "";

function downloadUrl(file: GeneratedFile): string {
  return `${API_BASE}/api/files?path=${encodeURIComponent(file.path)}`;
}

function previewUrl(file: GeneratedFile): string {
  return `${API_BASE}/api/files/preview?path=${encodeURIComponent(file.path)}`;
}

export function PreviewPane({ file, onClose }: { file: GeneratedFile; onClose: () => void }) {
  return (
    <div className="flex h-full flex-col bg-surface">
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <FileTypeIcon kind={file.kind} />
          <span className="truncate text-[14px] font-medium text-text">{file.name}</span>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <a
            href={downloadUrl(file)}
            download={file.name}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-text-muted transition-colors hover:bg-code-bg hover:text-text"
            aria-label="Download"
            title="Download"
          >
            <DownloadIcon />
          </a>
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-text-muted transition-colors hover:bg-code-bg hover:text-text"
            aria-label="Close preview"
            title="Close"
          >
            <CloseIcon />
          </button>
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-hidden">
        {file.kind === "pdf" ? (
          <PdfPreview file={file} />
        ) : file.kind === "xlsx" ? (
          <XlsxPreview file={file} />
        ) : (
          <UnsupportedPreview file={file} />
        )}
      </div>
    </div>
  );
}

function PdfPreview({ file }: { file: GeneratedFile }) {
  return (
    <iframe
      src={previewUrl(file)}
      title={file.name}
      className="h-full w-full border-0"
    />
  );
}

interface XlsxSheet {
  name: string;
  headers: string[];
  rows: (string | number)[][];
  total_rows: number;
  truncated: boolean;
}

function XlsxPreview({ file }: { file: GeneratedFile }) {
  const [sheets, setSheets] = useState<XlsxSheet[] | null>(null);
  const [activeSheet, setActiveSheet] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setSheets(null);
    setError(null);
    setActiveSheet(0);

    fetch(`${API_BASE}/api/files/xlsx-preview?path=${encodeURIComponent(file.path)}`)
      .then((res) => {
        if (!res.ok) throw new Error(`Server responded ${res.status}`);
        return res.json();
      })
      .then((data) => {
        if (!cancelled) setSheets(data.sheets ?? []);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Couldn't load preview.");
      });

    return () => {
      cancelled = true;
    };
  }, [file.path]);

  if (error) {
    return <div className="flex h-full items-center justify-center px-6 text-center text-[13px] text-text-muted">{error}</div>;
  }
  if (!sheets) {
    return <div className="flex h-full items-center justify-center text-[13px] text-text-muted">Loading…</div>;
  }
  if (sheets.length === 0) {
    return <div className="flex h-full items-center justify-center text-[13px] text-text-muted">This workbook has no sheets.</div>;
  }

  const sheet = sheets[Math.min(activeSheet, sheets.length - 1)];

  return (
    <div className="flex h-full flex-col">
      {sheets.length > 1 && (
        <div className="flex shrink-0 gap-1 overflow-x-auto border-b border-border px-3 py-2">
          {sheets.map((s, i) => (
            <button
              key={s.name}
              type="button"
              onClick={() => setActiveSheet(i)}
              className={`shrink-0 rounded-md px-2.5 py-1 text-[12.5px] transition-colors ${
                i === activeSheet ? "bg-accent text-accent-text" : "text-text-muted hover:bg-code-bg hover:text-text"
              }`}
            >
              {s.name}
            </button>
          ))}
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full border-collapse text-[13px]">
          <thead className="sticky top-0 bg-surface-raised">
            <tr>
              {sheet.headers.map((h, i) => (
                <th
                  key={i}
                  className="whitespace-nowrap border-b border-border px-3 py-2 text-left font-medium text-text"
                >
                  {h || `Column ${i + 1}`}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sheet.rows.map((row, rowIndex) => (
              <tr key={rowIndex} className="odd:bg-transparent even:bg-code-bg/40">
                {row.map((cell, cellIndex) => (
                  <td key={cellIndex} className="whitespace-nowrap border-b border-border/60 px-3 py-1.5 text-text-muted">
                    {String(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {sheet.truncated && (
          <div className="px-3 py-2 text-[12px] text-text-faint">
            Showing the first {sheet.rows.length + 1} of {sheet.total_rows} rows.
          </div>
        )}
      </div>
    </div>
  );
}

function UnsupportedPreview({ file }: { file: GeneratedFile }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
      <FileTypeIcon kind={file.kind} large />
      <p className="text-[13px] text-text-muted">
        No in-app preview for this file type yet — download it to view.
      </p>
      <a
        href={downloadUrl(file)}
        download={file.name}
        className="rounded-lg bg-accent px-4 py-2 text-[13px] font-medium text-accent-text"
      >
        Download {file.name}
      </a>
    </div>
  );
}

function FileTypeIcon({ kind, large }: { kind: GeneratedFile["kind"]; large?: boolean }) {
  const size = large ? 28 : 16;
  return (
    <span className={`flex shrink-0 items-center justify-center text-text-muted ${large ? "h-14 w-14 rounded-xl bg-code-bg" : ""}`}>
      <svg viewBox="0 0 20 20" width={size} height={size} fill="none">
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

function DownloadIcon() {
  return (
    <svg viewBox="0 0 16 16" width="15" height="15" fill="none">
      <path
        d="M8 2v8m0 0L5 7m3 3l3-3M3 12.5v1a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1v-1"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
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
