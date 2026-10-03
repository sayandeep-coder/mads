"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ChatInput, type ChatMode, type PromptSeed } from "@/components/ChatInput";
import { Message } from "@/components/Message";
import { PreviewPane } from "@/components/PreviewPane";
import { Sidebar, useSidebarCollapsed } from "@/components/Sidebar";
import { SplitLayout } from "@/components/SplitLayout";
import { TerminalPreviewPane } from "@/components/TerminalPreviewPane";
import { ToastHost } from "@/components/ToastHost";
import { useChat } from "@/lib/useChat";
import { useSessions } from "@/lib/useSessions";
import type { GeneratedFile, PreviewTarget } from "@/lib/types";

let nextSeedId = 1;
let nextRunId = 1;

export default function Home() {
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const { sessions, refresh, rename, remove } = useSessions();
  const [sidebarCollapsed, toggleSidebarCollapsed] = useSidebarCollapsed();
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  const handleSessionCreated = useCallback(
    (id: string) => {
      setActiveSessionId(id);
      refresh();
    },
    [refresh]
  );

  const { messages, sendMessage, isStreaming, error, stop, clearMessages } = useChat(
    activeSessionId,
    handleSessionCreated
  );
  const bottomRef = useRef<HTMLDivElement>(null);
  const [preview, setPreview] = useState<PreviewTarget>(null);
  const [promptSeed, setPromptSeed] = useState<PromptSeed | null>(null);
  const [mode, setMode] = useState<ChatMode>(null);

  const insertPrompt = useCallback((text: string) => {
    setPromptSeed({ text, id: nextSeedId++ });
  }, []);

  useEffect(() => {
    // "smooth" scrolling here is the wrong tool during active streaming:
    // messages (and, via the typewriter in Message.tsx, each message's own
    // revealed text) can change many times a second while a reply comes
    // in, and each change re-triggers this effect — stacking that many
    // concurrent smooth-scroll animations is exactly the kind of
    // compositor-thread pileup that can crash a tab's renderer outright.
    // A plain instant jump costs nothing per call and still keeps the
    // latest content in view.
    bottomRef.current?.scrollIntoView({ behavior: "auto", block: "end" });
  }, [messages]);

  const openPreview = (file: GeneratedFile) => setPreview(file);
  const closePreview = () => setPreview(null);
  const runCode = useCallback((language: string, code: string) => {
    setPreview({ kind: "code", language, code, id: nextRunId++ });
  }, []);

  const startNewChat = () => {
    setActiveSessionId(null);
    clearMessages();
    setPreview(null);
    setMobileSidebarOpen(false);
  };

  const selectSession = (id: string) => {
    setActiveSessionId(id);
    setPreview(null);
    setMobileSidebarOpen(false);
  };

  const deleteSession = (id: string) => {
    remove(id);
    if (id === activeSessionId) setActiveSessionId(null);
  };

  const sidebar = (
    <Sidebar
      sessions={sessions}
      activeSessionId={activeSessionId}
      onSelect={selectSession}
      onNewChat={startNewChat}
      onRename={rename}
      onDelete={deleteSession}
      onInsertPrompt={insertPrompt}
      collapsed={sidebarCollapsed}
      onToggleCollapsed={toggleSidebarCollapsed}
    />
  );

  const chat = (
    <div className="relative flex h-full flex-col overflow-hidden">
      <button
        type="button"
        onClick={() => setMobileSidebarOpen(true)}
        aria-label="Open sidebar"
        title="Open sidebar"
        className="absolute left-3 z-20 flex h-8 w-8 items-center justify-center rounded-md text-text-muted transition-colors hover:bg-user-bubble hover:text-text sm:hidden"
        style={{ top: "max(0.75rem, env(safe-area-inset-top))" }}
      >
        <MenuIcon />
      </button>

      <main className="flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <EmptyState onSend={sendMessage} disabled={isStreaming} seed={promptSeed} mode={mode} onModeChange={setMode} />
        ) : (
          <div className="mx-auto flex min-h-full w-full max-w-3xl flex-col gap-6 px-4 py-6 sm:px-6">
            {messages.map((m) => (
              <Message key={m.id} message={m} onOpenFile={openPreview} onRunCode={runCode} />
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

      {messages.length > 0 && (
        <ChatInput
          onSend={sendMessage}
          disabled={isStreaming}
          onStop={stop}
          seed={promptSeed}
          mode={mode}
          onModeChange={setMode}
        />
      )}
    </div>
  );

  return (
    <div className="flex h-full w-full overflow-hidden">
      <div className="hidden h-full sm:flex">{sidebar}</div>

      {mobileSidebarOpen && (
        <div className="fixed inset-0 z-50 flex sm:hidden">
          <div className="absolute inset-0 bg-black/50" onClick={() => setMobileSidebarOpen(false)} />
          <div className="relative h-full">
            <Sidebar
              sessions={sessions}
              activeSessionId={activeSessionId}
              onSelect={selectSession}
              onNewChat={startNewChat}
              onRename={rename}
              onDelete={deleteSession}
              onInsertPrompt={insertPrompt}
              collapsed={false}
              onToggleCollapsed={toggleSidebarCollapsed}
              onCloseMobile={() => setMobileSidebarOpen(false)}
            />
          </div>
        </div>
      )}

      <div className="h-full min-w-0 flex-1">
        <SplitLayout
          left={chat}
          right={
            preview === null ? null : preview.kind === "code" ? (
              <TerminalPreviewPane target={preview} onClose={closePreview} />
            ) : (
              <PreviewPane file={preview} onClose={closePreview} />
            )
          }
        />
      </div>

      <ToastHost />
    </div>
  );
}

function EmptyState({
  onSend,
  disabled,
  seed,
  mode,
  onModeChange,
}: {
  onSend: (prompt: string, file?: File, mode?: ChatMode) => void;
  disabled: boolean;
  seed: PromptSeed | null;
  mode: ChatMode;
  onModeChange: (mode: ChatMode) => void;
}) {
  return (
    <section className="mads-hero relative flex min-h-full items-center justify-center overflow-hidden px-4 py-16 sm:px-8">
      <div className="mads-hero-glow" aria-hidden="true" />
      <div className="relative z-10 flex w-full max-w-2xl flex-col items-center text-center">
        <h1 className="text-balance text-[22px] font-normal leading-[1.25] tracking-normal text-text sm:text-[26px]">
          Hi Sayandeep, what&apos;s the plan?
        </h1>

        <div className="mt-6 w-full sm:mt-7">
          <ChatInput onSend={onSend} disabled={disabled} variant="hero" seed={seed} mode={mode} onModeChange={onModeChange} />
        </div>
      </div>
    </section>
  );
}

function MenuIcon() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" fill="none">
      <path d="M2.5 4.5h11M2.5 8h11M2.5 11.5h11" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}
