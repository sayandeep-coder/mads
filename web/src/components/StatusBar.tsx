"use client";

import Image from "next/image";

export function StatusBar({
  onNewChat,
}: {
  onNewChat: () => void | Promise<void>;
}) {
  return (
    <header
      className="relative z-20 flex items-center justify-between border-b border-border/80 bg-bg/70 px-4 py-3 backdrop-blur-xl sm:px-6"
      style={{ paddingTop: "max(0.75rem, env(safe-area-inset-top))" }}
    >
      <div className="flex items-center gap-2.5">
        <Image
          src="/mads-icon.png"
          alt=""
          width="30"
          height="30"
          className="h-[30px] w-[30px] rounded-[9px] object-cover"
        />
        <span className="text-[15px] font-semibold tracking-tight text-text">Mads</span>
      </div>
      <button
        type="button"
        onClick={onNewChat}
        aria-label="Start a new chat"
        title="New chat"
        className="flex h-9 w-9 items-center justify-center rounded-full text-text-muted transition-colors hover:bg-user-bubble hover:text-text active:scale-95"
      >
        <PencilIcon />
      </button>
    </header>
  );
}

function PencilIcon() {
  return (
    <svg viewBox="0 0 20 20" width="17" height="17" fill="none" aria-hidden="true">
      <path
        d="M12.9 4.1 15.9 7.1M4.25 15.75l.7-3.15L13.65 3.9a1.4 1.4 0 0 1 2 0l.45.45a1.4 1.4 0 0 1 0 2l-8.7 8.7-3.15.7Z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
