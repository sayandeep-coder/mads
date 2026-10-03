"use client";

import type { JSX } from "react";
import { useEffect, useRef, useState, type ChangeEvent, type KeyboardEvent } from "react";

/** A one-shot request to seed the composer with starter text (e.g. the
 * sidebar's "Image" nav item) and focus it. `id` just needs to change for
 * the same text to be re-appliable — see the effect below. */
export interface PromptSeed {
  text: string;
  id: number;
}

export type ChatMode = "study" | "research" | null;

const MODE_META: Record<Exclude<ChatMode, null>, { label: string; Icon: (props: { className?: string }) => JSX.Element }> = {
  study: { label: "Study mode", Icon: CapIcon },
  research: { label: "Research mode", Icon: FlaskIcon },
};

const EXTENSION_META: Record<string, (props: { className?: string }) => JSX.Element> = {
  pdf: PdfGlyph,
  doc: DocGlyph,
  docx: DocGlyph,
  xls: XlsGlyph,
  xlsx: XlsGlyph,
  csv: XlsGlyph,
  ppt: PptGlyph,
  pptx: PptGlyph,
  png: ImageGlyph,
  jpg: ImageGlyph,
  jpeg: ImageGlyph,
  webp: ImageGlyph,
};

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** "Really-Long-Filename-Here.xlsx" -> "Really-Long-F….xlsx" — keeps the
 * extension visible (it's the useful part once truncated) instead of
 * relying on a plain CSS ellipsis, which would just lop off the end. */
function shortenFileName(name: string, maxBase = 14): string {
  const dot = name.lastIndexOf(".");
  const base = dot > 0 ? name.slice(0, dot) : name;
  const ext = dot > 0 ? name.slice(dot) : "";
  if (base.length <= maxBase) return name;
  return `${base.slice(0, maxBase)}…${ext}`;
}

export function ChatInput({
  onSend,
  disabled,
  onStop,
  variant = "default",
  seed,
  mode = null,
  onModeChange,
}: {
  onSend: (text: string, file?: File, mode?: ChatMode) => void;
  disabled: boolean;
  /** Aborts the in-flight reply. When provided, the send button becomes a stop button while `disabled` is true (mirrors Claude's input: a filled square replacing the arrow mid-stream, clickable to cancel). */
  onStop?: () => void;
  variant?: "default" | "hero";
  /** A starter prompt to drop into the composer from outside (e.g. the sidebar's "Image" action). */
  seed?: PromptSeed | null;
  /** The active conversation mode — lifted to the page so it survives this
   * composer unmounting (hero vs. default variant swap on first message). */
  mode?: ChatMode;
  onModeChange?: (mode: ChatMode) => void;
}) {
  const [value, setValue] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const lastSeedId = useRef<number | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const resize = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  };

  useEffect(() => {
    if (!seed || seed.id === lastSeedId.current) return;
    lastSeedId.current = seed.id;
    setValue(seed.text);
    const el = textareaRef.current;
    if (el) {
      el.focus();
      requestAnimationFrame(() => {
        resize();
        el.setSelectionRange(el.value.length, el.value.length);
      });
    }
  }, [seed]);

  useEffect(() => {
    if (!menuOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [menuOpen]);

  const submit = () => {
    if (disabled) return;
    if (!value.trim() && !file) return;
    onSend(value.trim() || `About this file: ${file?.name}`, file ?? undefined, mode);
    setValue("");
    setFile(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  };

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const picked = e.target.files?.[0];
    setFile(picked ?? null);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const toggleMode = (next: Exclude<ChatMode, null>) => {
    onModeChange?.(mode === next ? null : next);
    setMenuOpen(false);
  };

  const extension = file?.name.split(".").pop()?.toLowerCase() ?? "";
  const FileIcon = EXTENSION_META[extension] ?? GenericFileGlyph;
  const activeModeMeta = mode ? MODE_META[mode] : null;

  return (
    <div
      className={`relative z-20 mx-auto w-full max-w-3xl ${variant === "hero" ? "px-0" : "px-4 sm:px-6"}`}
      style={
        variant === "default"
          ? { paddingBottom: "max(1rem, env(safe-area-inset-bottom))" }
          : undefined
      }
    >
      <div className="flex flex-col gap-2 rounded-[28px] border border-border bg-surface p-3 shadow-[0_8px_30px_rgba(0,0,0,0.25)] transition-colors focus-within:border-border-strong">
        {(file || activeModeMeta) && (
          <div className="flex flex-wrap items-center gap-2">
            {file && (
              <div className="flex items-center gap-2.5 rounded-2xl bg-surface-raised py-2 pl-2 pr-3 shadow-sm">
                <FileIcon className="h-9 w-9 shrink-0" />
                <div className="flex min-w-0 flex-col">
                  <span className="text-[13px] font-medium text-text">{shortenFileName(file.name)}</span>
                  <span className="text-[11px] text-text-muted">{formatSize(file.size)}</span>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setFile(null);
                    if (fileInputRef.current) fileInputRef.current.value = "";
                  }}
                  aria-label="Remove attached file"
                  className="ml-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-text-faint hover:bg-user-bubble hover:text-text"
                >
                  <svg viewBox="0 0 16 16" width="10" height="10" fill="none">
                    <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                  </svg>
                </button>
              </div>
            )}
            {activeModeMeta && (
              <div className="flex items-center gap-2 rounded-full bg-accent/15 py-1.5 pl-3 pr-2 text-accent">
                <activeModeMeta.Icon className="h-4 w-4" />
                <span className="text-[13px] font-medium">{activeModeMeta.label}</span>
                <button
                  type="button"
                  onClick={() => onModeChange?.(null)}
                  aria-label={`Turn off ${activeModeMeta.label}`}
                  className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-accent/70 hover:bg-accent/15 hover:text-accent"
                >
                  <svg viewBox="0 0 16 16" width="10" height="10" fill="none">
                    <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                  </svg>
                </button>
              </div>
            )}
          </div>
        )}

        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            resize();
          }}
          onKeyDown={handleKeyDown}
          placeholder={disabled ? "Mads is replying…" : "Ask Mads"}
          rows={1}
          disabled={disabled}
          autoComplete="off"
          autoCorrect="off"
          autoCapitalize="sentences"
          spellCheck={false}
          data-ms-editor="false"
          className="chat-input max-h-[200px] w-full resize-none bg-transparent px-1 py-1 text-[15px] leading-6 text-text placeholder:text-text-faint disabled:cursor-not-allowed disabled:opacity-60"
        />

        <div className="flex items-center justify-between">
          <div ref={menuRef} className="relative">
            {menuOpen && (
              <div className="absolute bottom-full left-0 mb-2 w-52 rounded-xl border border-border bg-surface-raised p-1 shadow-xl">
                <input
                  ref={fileInputRef}
                  type="file"
                  onChange={handleFileChange}
                  disabled={disabled}
                  className="hidden"
                />
                <button
                  type="button"
                  onClick={() => {
                    fileInputRef.current?.click();
                    setMenuOpen(false);
                  }}
                  className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] text-text transition-colors hover:bg-user-bubble"
                >
                  <PaperclipIcon className="h-4 w-4 text-text-muted" />
                  Attach file
                </button>
                <div className="my-1 border-t border-border" />
                <button
                  type="button"
                  onClick={() => toggleMode("study")}
                  className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] transition-colors hover:bg-user-bubble ${
                    mode === "study" ? "text-accent" : "text-text"
                  }`}
                >
                  <CapIcon className="h-4 w-4" />
                  Study mode
                  {mode === "study" && <CheckIcon className="ml-auto h-3.5 w-3.5" />}
                </button>
                <button
                  type="button"
                  onClick={() => toggleMode("research")}
                  className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] transition-colors hover:bg-user-bubble ${
                    mode === "research" ? "text-accent" : "text-text"
                  }`}
                >
                  <FlaskIcon className="h-4 w-4" />
                  Research mode
                  {mode === "research" && <CheckIcon className="ml-auto h-3.5 w-3.5" />}
                </button>
              </div>
            )}

            <button
              type="button"
              onClick={() => setMenuOpen((v) => !v)}
              disabled={disabled}
              aria-label="Attach file or set a mode"
              title="Attach file or set a mode"
              aria-expanded={menuOpen}
              className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full border transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
                menuOpen
                  ? "border-border-strong text-text"
                  : "border-border/80 text-text-muted hover:border-border-strong hover:text-text"
              }`}
            >
              <svg viewBox="0 0 16 16" width="15" height="15" fill="none">
                <path d="M8 3.5v9M3.5 8h9" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              </svg>
            </button>
          </div>

          {disabled && onStop ? (
            <button
              type="button"
              onClick={onStop}
              aria-label="Stop generating"
              title="Stop"
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent text-accent-text transition-colors hover:bg-accent-hover"
            >
              <span className="h-2.5 w-2.5 rounded-[2.5px] bg-current" />
            </button>
          ) : (
            <button
              type="button"
              onClick={submit}
              disabled={disabled || (!value.trim() && !file)}
              aria-label="Send message"
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent text-accent-text transition-colors hover:bg-accent-hover disabled:opacity-30"
            >
              <SendIcon />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/** Shared document silhouette (folded top-right corner) that each
 * file-type glyph below fills in its own brand color — these are original
 * renderings, not copies of any vendor's actual logo artwork. */
function DocShape({ fill, corner }: { fill: string; corner: string }) {
  return (
    <>
      <path d="M5 2.5h9l5 5V21a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1Z" fill={fill} />
      <path d="M14 2.5V7a1 1 0 0 0 1 1h4.5" fill={corner} />
    </>
  );
}

/** Solid arrow (stem + triangular head) rather than a thin stroked chevron
 * — same idea as Claude's own send glyph, a shape distinct enough to read
 * instantly at 16px instead of blending into every other outline icon in
 * the composer. */
function SendIcon() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" fill="none">
      <path
        d="M8 2.2c.33 0 .64.16.83.44l4.3 6.2a1 1 0 0 1-.83 1.57H9.3V13a1 1 0 0 1-2 0V10.4H4.3a1 1 0 0 1-.83-1.57l4.3-6.2c.19-.28.5-.44.83-.44Z"
        fill="currentColor"
      />
    </svg>
  );
}

function PaperclipIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" className={className} fill="none">
      <path
        d="M11.5 4.5l-5 5a1.8 1.8 0 0 0 2.5 2.5l5-5a3.2 3.2 0 0 0-4.5-4.5l-5.2 5.2a4.5 4.5 0 0 0 6.4 6.4l4.3-4.3"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function CapIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" className={className} fill="none">
      <path d="M8 2.5l6.5 3.25L8 9l-6.5-3.25Z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
      <path d="M4.5 7.1v3c0 1 1.5 1.9 3.5 1.9s3.5-.9 3.5-1.9v-3" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
      <path d="M14.5 5.75V9.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  );
}

function FlaskIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" className={className} fill="none">
      <path
        d="M6.3 2.5h3.4M6.8 2.5v4l-3.3 5.8a1.3 1.3 0 0 0 1.1 2h6.8a1.3 1.3 0 0 0 1.1-2L9.2 6.5v-4"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M5.2 9.8h5.6" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" />
    </svg>
  );
}

function CheckIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" className={className} fill="none">
      <path d="M3.5 8.5l2.5 2.5L12.5 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function PdfGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" className={className}>
      <DocShape fill="#e8503f" corner="#f4a69c" />
      <text x="12" y="18" textAnchor="middle" fontSize="7" fontWeight="700" fontFamily="sans-serif" fill="#ffffff">
        PDF
      </text>
    </svg>
  );
}

function DocGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" className={className}>
      <DocShape fill="#2f6fed" corner="#9db9f6" />
      <text x="12" y="18" textAnchor="middle" fontSize="7" fontWeight="700" fontFamily="sans-serif" fill="#ffffff">
        DOC
      </text>
    </svg>
  );
}

function XlsGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" className={className}>
      <DocShape fill="#1a9e5c" corner="#8fd6b2" />
      <text x="12" y="18" textAnchor="middle" fontSize="7" fontWeight="700" fontFamily="sans-serif" fill="#ffffff">
        XLS
      </text>
    </svg>
  );
}

function PptGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" className={className}>
      <DocShape fill="#d96b2e" corner="#f0bb94" />
      <text x="12" y="18" textAnchor="middle" fontSize="7" fontWeight="700" fontFamily="sans-serif" fill="#ffffff">
        PPT
      </text>
    </svg>
  );
}

function ImageGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" className={className}>
      <rect x="2" y="3.5" width="20" height="17" rx="2.5" fill="#8a5ce0" />
      <circle cx="8.5" cy="9.5" r="2" fill="#ffffff" />
      <path
        d="M3.5 18.5l5.8-5.8a1.5 1.5 0 0 1 2.1 0L16 17.2l1.2-1.2a1.5 1.5 0 0 1 2.1 0l1.7 1.7"
        stroke="#ffffff"
        strokeWidth="1.5"
        fill="none"
      />
    </svg>
  );
}

function GenericFileGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" className={className} fill="none">
      <path
        d="M5 2.5h9l5 5V21a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1Z"
        stroke="var(--text-faint)"
        strokeWidth="1.6"
      />
      <path d="M14 2.5V7a1 1 0 0 0 1 1h4.5" stroke="var(--text-faint)" strokeWidth="1.6" />
    </svg>
  );
}
