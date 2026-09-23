"use client";

import { useRef, useState, type KeyboardEvent } from "react";

export function ChatInput({
  onSend,
  disabled,
  variant = "default",
}: {
  onSend: (text: string) => void;
  disabled: boolean;
  variant?: "default" | "hero";
}) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const submit = () => {
    if (!value.trim() || disabled) return;
    onSend(value);
    setValue("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
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
        className={`flex items-end gap-2 border bg-surface transition-all focus-within:border-border-strong ${
          variant === "hero"
            ? "min-h-[150px] rounded-[28px] border-white/70 p-4 shadow-[0_22px_65px_rgba(66,39,83,0.2)] sm:min-h-[168px] sm:p-5"
            : "rounded-[20px] border-border/90 bg-surface/90 p-2.5 shadow-[0_10px_35px_rgba(60,52,40,0.08),0_1px_2px_rgba(0,0,0,0.04)] backdrop-blur-xl focus-within:shadow-[0_12px_40px_rgba(60,52,40,0.11)]"
        }`}
      >
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
        <button
          type="button"
          onClick={submit}
          disabled={disabled || !value.trim()}
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
      </div>
    </div>
  );
}
