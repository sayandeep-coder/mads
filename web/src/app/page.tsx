"use client";

import { useEffect, useRef } from "react";
import { ChatInput } from "@/components/ChatInput";
import { Message } from "@/components/Message";
import { StatusBar } from "@/components/StatusBar";
import { useChat } from "@/lib/useChat";

export default function Home() {
  const { messages, sendMessage, isStreaming, error, newChat } = useChat();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <StatusBar onNewChat={newChat} />

      <main className="flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <EmptyState onSend={sendMessage} disabled={isStreaming} />
        ) : (
          <div className="mx-auto flex min-h-full w-full max-w-3xl flex-col gap-6 px-4 py-6 sm:px-6">
            {messages.map((m) => (
              <Message key={m.id} message={m} />
            ))}
            {error && (
              <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-[13px] text-danger">
                {error}
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        )}
      </main>

      {messages.length > 0 && <ChatInput onSend={sendMessage} disabled={isStreaming} />}
    </div>
  );
}

function EmptyState({
  onSend,
  disabled,
}: {
  onSend: (prompt: string) => void;
  disabled: boolean;
}) {
  return (
    <section className="mads-hero relative flex min-h-full items-center justify-center overflow-hidden px-4 py-16 sm:px-8">
      <div className="mads-hero-glow" aria-hidden="true" />
      <div className="relative z-10 flex w-full max-w-4xl flex-col items-center text-center">
        <h1 className="text-balance text-[38px] font-semibold leading-[1.04] tracking-[-0.05em] text-[#242321] sm:text-[56px] md:text-[64px]">
          Make anything happen
        </h1>
        <p className="mt-3 text-[15px] font-medium text-[#454446]/75 sm:text-[18px]">
          Plan it, research it, or get it done.
        </p>

        <div className="mt-9 w-full sm:mt-11">
          <ChatInput onSend={onSend} disabled={disabled} variant="hero" />
        </div>

        <div className="mt-5 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-[11px] font-medium text-[#343236]/55 sm:text-[12px]">
          <span>Works with your tools</span>
          <span className="h-1 w-1 rounded-full bg-[#343236]/30" />
          <span>Shows its work</span>
          <span className="h-1 w-1 rounded-full bg-[#343236]/30" />
          <span>Built around you</span>
        </div>
      </div>
    </section>
  );
}
