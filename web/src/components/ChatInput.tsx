"use client";

import { useRef, useState, type ChangeEvent, type KeyboardEvent } from "react";

export function ChatInput({
  onSend,
  disabled,
  onStop,
  variant = "default",
}: {
  onSend: (text: string, file?: File) => void;
  disabled: boolean;
  /** Aborts the in-flight reply. When provided, the send button becomes a stop button while `disabled` is true (mirrors Claude's input: a filled square replacing the arrow mid-stream, clickable to cancel). */
  onStop?: () => void;
  variant?: "default" | "hero";
}) {
  const [value, setValue] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const submit = () => {
    if (disabled) return;
    if (!value.trim() && !file) return;
    onSend(value.trim() || `About this file: ${file?.name}`, file ?? undefined);
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

  const handleInput = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  };

  return (
    <div
      className={`relative z-20 mx-auto w-full max-w-3xl ${variant === "hero" ? "px-0" : "px-4 sm:px-6"}`}
      style={
        variant === "default"
          ? { paddingBottom: "max(1rem, env(safe-area-inset-bottom))" }
          : undefined
      }
    >
      <div
        className={`flex flex-col border bg-surface transition-all focus-within:border-border-strong ${
          variant === "hero"
            ? "min-h-[150px] rounded-[28px] border-white/70 p-4 shadow-[0_22px_65px_rgba(66,39,83,0.2)] sm:min-h-[168px] sm:p-5"
            : "rounded-[20px] border-border/90 bg-surface/90 p-2.5 shadow-[0_10px_35px_rgba(60,52,40,0.08),0_1px_2px_rgba(0,0,0,0.04)] backdrop-blur-xl focus-within:shadow-[0_12px_40px_rgba(60,52,40,0.11)]"
        }`}
      >
        {file && (
          <div className="mb-2 flex items-center gap-2 self-start rounded-full border border-border/80 bg-code-bg px-3 py-1 text-[13px] text-text-muted">
            <FileChipIcon />
            <span className="max-w-[220px] truncate">{file.name}</span>
            <button
              type="button"
              onClick={() => {
                setFile(null);
                if (fileInputRef.current) fileInputRef.current.value = "";
              }}
              aria-label="Remove attached file"
              className="text-text-faint hover:text-text"
            >
              <svg viewBox="0 0 16 16" width="11" height="11" fill="none">
                <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            </button>
          </div>
        )}

        <div className="flex items-end gap-2">
          <input
            ref={fileInputRef}
            type="file"
            onChange={handleFileChange}
            disabled={disabled}
            className="hidden"
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={disabled}
            aria-label="Attach a file"
            title="Attach a file"
            className={`flex shrink-0 items-center justify-center rounded-full border border-border/80 text-text-muted transition-colors hover:border-border-strong hover:text-text disabled:cursor-not-allowed disabled:opacity-40 ${
              variant === "hero" ? "h-10 w-10" : "h-8 w-8"
            }`}
          >
            <svg viewBox="0 0 16 16" width="15" height="15" fill="none">
              <path d="M8 3.5v9M3.5 8h9" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
          </button>

          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => {
              setValue(e.target.value);
              handleInput();
            }}
            onKeyDown={handleKeyDown}
            placeholder={
              disabled
                ? "Mads is replying…"
                : variant === "hero"
                  ? "Ask Mads to plan, research, write, or build something…"
                  : "Message Mads…"
            }
            rows={1}
            disabled={disabled}
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="sentences"
            spellCheck={false}
            data-ms-editor="false"
            className={`chat-input max-h-[200px] flex-1 resize-none bg-transparent text-text placeholder:text-text-faint disabled:cursor-not-allowed disabled:opacity-60 ${
              variant === "hero"
                ? "self-stretch px-1 py-1 text-[16px] leading-relaxed sm:text-[17px]"
                : "px-2 py-1.5 text-[16px] leading-relaxed"
            }`}
          />
          {disabled && onStop ? (
            <button
              type="button"
              onClick={onStop}
              aria-label="Stop generating"
              title="Stop"
              className={`flex shrink-0 items-center justify-center rounded-full text-accent-text transition-all ${
                variant === "hero" ? "h-10 w-10 bg-[#29282a] hover:bg-black" : "h-8 w-8 bg-accent"
              }`}
            >
              <span className="h-2.5 w-2.5 rounded-[2.5px] bg-current" />
            </button>
          ) : (
            <button
              type="button"
              onClick={submit}
              disabled={disabled || (!value.trim() && !file)}
              aria-label="Send message"
              className={`flex shrink-0 items-center justify-center rounded-full text-accent-text transition-all disabled:opacity-30 ${
                variant === "hero"
                  ? "h-10 w-10 bg-[#29282a] hover:scale-105 hover:bg-black"
                  : "h-8 w-8 bg-accent"
              }`}
            >
              <svg viewBox="0 0 16 16" width="16" height="16" fill="none">
                <path
                  d="M8 13V3M8 3L3.5 7.5M8 3l4.5 4.5"
                  stroke="currentColor"
                  strokeWidth="1.75"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function FileChipIcon() {
  return (
    <svg viewBox="0 0 16 16" width="12" height="12" fill="none" className="shrink-0">
      <path
        d="M6 2.5h5.5L15.5 6.5V16a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1Z"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinejoin="round"
      />
    </svg>
  );
}
