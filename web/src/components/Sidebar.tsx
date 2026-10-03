"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import type { ChatSession } from "@/lib/types";
import { API_BASE } from "@/lib/useChat";
import { toast } from "@/lib/toast";
import { useTheme } from "@/lib/useTheme";

const USER_NAME = "Sayandeep Purkait";

const STORAGE_KEY = "mads_sidebar_collapsed";

function groupSessions(sessions: ChatSession[]) {
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime() / 1000;
  const startOfYesterday = startOfToday - 86400;
  const startOfWeek = startOfToday - 6 * 86400;
  const startOfMonth = startOfToday - 29 * 86400;

  const groups: { label: string; items: ChatSession[] }[] = [
    { label: "Today", items: [] },
    { label: "Yesterday", items: [] },
    { label: "Previous 7 days", items: [] },
    { label: "Previous 30 days", items: [] },
    { label: "Older", items: [] },
  ];

  for (const session of sessions) {
    if (session.updated_at >= startOfToday) groups[0].items.push(session);
    else if (session.updated_at >= startOfYesterday) groups[1].items.push(session);
    else if (session.updated_at >= startOfWeek) groups[2].items.push(session);
    else if (session.updated_at >= startOfMonth) groups[3].items.push(session);
    else groups[4].items.push(session);
  }

  return groups.filter((g) => g.items.length > 0);
}

export function Sidebar({
  sessions,
  activeSessionId,
  onSelect,
  onNewChat,
  onRename,
  onDelete,
  onInsertPrompt,
  collapsed,
  onToggleCollapsed,
  onCloseMobile,
}: {
  sessions: ChatSession[];
  activeSessionId: string | null;
  onSelect: (id: string) => void;
  onNewChat: () => void;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
  /** Seeds the chat composer with a starter prompt (used by the "Image" nav item) and focuses it. */
  onInsertPrompt: (text: string) => void;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  onCloseMobile?: () => void;
}) {
  const [query, setQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const editInputRef = useRef<HTMLInputElement>(null);
  const [theme, setTheme] = useTheme();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const settingsRef = useRef<HTMLDivElement>(null);

  const handleConnectGoogle = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/status`);
      if (!res.ok) throw new Error();
      const data = await res.json();
      const connected = (data.connected_servers ?? []) as string[];
      if (connected.includes("google_workspace")) {
        toast("Google is already connected");
      } else {
        toast("Google isn't connected — add credentials in .env and restart Mads");
      }
    } catch {
      toast("Couldn't reach Mads to check Google's connection");
    }
  };

  const handleInsertImage = () => {
    onInsertPrompt("Create an image of ");
    onCloseMobile?.();
  };

  useEffect(() => {
    if (!settingsOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (settingsRef.current && !settingsRef.current.contains(e.target as Node)) setSettingsOpen(false);
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [settingsOpen]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return sessions;
    return sessions.filter((s) => s.title.toLowerCase().includes(q) || s.preview?.toLowerCase().includes(q));
  }, [sessions, query]);

  const groups = useMemo(() => groupSessions(filtered), [filtered]);

  const startEditing = (session: ChatSession) => {
    setEditingId(session.id);
    setEditValue(session.title);
    setConfirmDeleteId(null);
    requestAnimationFrame(() => editInputRef.current?.select());
  };

  const commitEdit = () => {
    if (editingId) {
      const trimmed = editValue.trim();
      if (trimmed) onRename(editingId, trimmed);
    }
    setEditingId(null);
  };

  const handleEditKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") commitEdit();
    if (e.key === "Escape") setEditingId(null);
  };

  if (collapsed) {
    return (
      <div className="flex h-full w-[60px] flex-col items-center gap-3 border-r border-sidebar-border bg-sidebar py-3">
        <button
          type="button"
          onClick={onToggleCollapsed}
          aria-label="Expand sidebar"
          title="Expand sidebar"
          className="flex h-9 w-9 items-center justify-center rounded-full text-sidebar-text-muted transition-colors hover:bg-sidebar-hover hover:text-sidebar-text"
        >
          <SidebarIcon />
        </button>
        <button
          type="button"
          onClick={onNewChat}
          aria-label="New chat"
          title="New chat"
          className="flex h-9 w-9 items-center justify-center rounded-full text-sidebar-text-muted transition-colors hover:bg-sidebar-hover hover:text-sidebar-text"
        >
          <NewChatIcon />
        </button>
        <button
          type="button"
          onClick={() => {
            onToggleCollapsed();
            setSearchOpen(true);
          }}
          aria-label="Search chats"
          title="Search chats"
          className="flex h-9 w-9 items-center justify-center rounded-full text-sidebar-text-muted transition-colors hover:bg-sidebar-hover hover:text-sidebar-text"
        >
          <SearchIcon />
        </button>
        <Link
          href="/tools"
          aria-label="Tools"
          title="Tools"
          className="flex h-9 w-9 items-center justify-center rounded-full text-sidebar-text-muted transition-colors hover:bg-sidebar-hover hover:text-sidebar-text"
        >
          <ToolsIcon />
        </Link>
        <button
          type="button"
          onClick={handleInsertImage}
          aria-label="Image"
          title="Image"
          className="flex h-9 w-9 items-center justify-center rounded-full text-sidebar-text-muted transition-colors hover:bg-sidebar-hover hover:text-sidebar-text"
        >
          <ImageIcon />
        </button>
        <button
          type="button"
          onClick={handleConnectGoogle}
          aria-label="Connect"
          title="Connect"
          className="flex h-9 w-9 items-center justify-center rounded-full text-sidebar-text-muted transition-colors hover:bg-sidebar-hover hover:text-sidebar-text"
        >
          <ConnectIcon />
        </button>
        <div className="mt-auto">
          <button
            type="button"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            aria-label="Toggle theme"
            title="Toggle theme"
            className="flex h-9 w-9 items-center justify-center rounded-full text-sidebar-text-muted transition-colors hover:bg-sidebar-hover hover:text-sidebar-text"
          >
            {theme === "dark" ? <SunIcon /> : <MoonIcon />}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full w-[220px] shrink-0 flex-col border-r border-sidebar-border bg-sidebar">
      <div className="flex items-center gap-2 px-3 pt-3">
        {/* Plain <img>, not next/image — the optimizer caches rendered
            output under _next/image keyed loosely enough that swapping
            this file's bytes in place kept serving the old cached icon. */}
        <img
          src="/mads-icon.png"
          alt=""
          width={20}
          height={20}
          className="h-5 w-5 rounded-[6px] object-cover"
        />
        <span className="text-[13px] font-medium text-sidebar-text">Mads</span>
        <div className="ml-auto flex items-center gap-1">
          {onCloseMobile && (
            <button
              type="button"
              onClick={onCloseMobile}
              aria-label="Close sidebar"
              className="flex h-8 w-8 items-center justify-center rounded-full text-sidebar-text-muted hover:bg-sidebar-hover hover:text-sidebar-text sm:hidden"
            >
              <CloseIcon />
            </button>
          )}
          <button
            type="button"
            onClick={onToggleCollapsed}
            aria-label="Collapse sidebar"
            title="Collapse sidebar"
            className="hidden h-8 w-8 items-center justify-center rounded-full text-sidebar-text-muted transition-colors hover:bg-sidebar-hover hover:text-sidebar-text sm:flex"
          >
            <SidebarIcon />
          </button>
        </div>
      </div>

      <div className="flex flex-col gap-0.5 px-3 pt-3">
        <button
          type="button"
          onClick={onNewChat}
          className={`flex items-center gap-3 rounded-full px-3 py-2 text-[13px] transition-colors ${
            activeSessionId === null
              ? "bg-sidebar-active font-semibold text-sidebar-text"
              : "font-normal text-sidebar-text hover:bg-sidebar-hover"
          }`}
        >
          <NewChatIcon />
          New chat
        </button>

        {searchOpen ? (
          <div className="flex items-center gap-3 rounded-full bg-sidebar-input px-3 py-2 transition-colors focus-within:bg-sidebar-hover">
            <SearchIcon />
            <input
              ref={searchInputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onBlur={() => {
                if (!query) setSearchOpen(false);
              }}
              placeholder="Search chats"
              className="sidebar-search-input w-full bg-transparent text-[13px] text-sidebar-text placeholder:text-sidebar-text-faint outline-none"
            />
          </div>
        ) : (
          <button
            type="button"
            onClick={() => {
              setSearchOpen(true);
              requestAnimationFrame(() => searchInputRef.current?.focus());
            }}
            className="flex items-center gap-3 rounded-full px-3 py-2 text-left text-[13px] font-normal text-sidebar-text transition-colors hover:bg-sidebar-hover"
          >
            <SearchIcon />
            Search chats
          </button>
        )}

        <Link
          href="/tools"
          onClick={() => onCloseMobile?.()}
          className="flex items-center gap-3 rounded-full px-3 py-2 text-left text-[13px] font-normal text-sidebar-text transition-colors hover:bg-sidebar-hover"
        >
          <ToolsIcon />
          Tools
        </Link>
        <button
          type="button"
          onClick={handleInsertImage}
          className="flex items-center gap-3 rounded-full px-3 py-2 text-left text-[13px] font-normal text-sidebar-text transition-colors hover:bg-sidebar-hover"
        >
          <ImageIcon />
          Image
        </button>
        <button
          type="button"
          onClick={handleConnectGoogle}
          className="flex items-center gap-3 rounded-full px-3 py-2 text-left text-[13px] font-normal text-sidebar-text transition-colors hover:bg-sidebar-hover"
        >
          <ConnectIcon />
          Connect
        </button>
      </div>

      <nav className="mt-3 flex-1 overflow-y-auto px-3 pb-3">
        {groups.length === 0 && (
          <p className="px-3 py-6 text-center text-[13px] text-sidebar-text-faint">
            {query ? "No matching chats" : "No chats yet"}
          </p>
        )}
        {groups.map((group, i) => (
          <div key={group.label} className={i === 0 ? "" : "mt-2"}>
            <div className="px-3 pb-1 pt-3 text-[11px] font-normal text-sidebar-text-faint">{group.label}</div>
            <ul className="flex flex-col gap-0.5">
              {group.items.map((session) => {
                const isActive = session.id === activeSessionId;
                const isEditing = editingId === session.id;
                return (
                  <li key={session.id} className="group relative">
                    {isEditing ? (
                      <input
                        ref={editInputRef}
                        value={editValue}
                        autoFocus
                        onChange={(e) => setEditValue(e.target.value)}
                        onBlur={commitEdit}
                        onKeyDown={handleEditKeyDown}
                        className="w-full rounded-full border border-accent/60 bg-sidebar-input px-3 py-2 text-[13px] text-sidebar-text outline-none"
                      />
                    ) : (
                      <button
                        type="button"
                        onClick={() => onSelect(session.id)}
                        onDoubleClick={() => startEditing(session)}
                        className={`flex w-full items-center rounded-full px-3 py-2 text-left text-[13px] transition-colors ${
                          isActive
                            ? "bg-sidebar-active text-sidebar-text"
                            : "text-sidebar-text-muted hover:bg-sidebar-hover hover:text-sidebar-text"
                        }`}
                      >
                        <span className="min-w-0 flex-1 truncate pr-12">{session.title || "New chat"}</span>
                      </button>
                    )}

                    {!isEditing && (
                      <div className="absolute right-2 top-1/2 flex -translate-y-1/2 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            startEditing(session);
                          }}
                          aria-label="Rename chat"
                          title="Rename"
                          className="flex h-7 w-7 items-center justify-center rounded-full text-sidebar-text-faint hover:bg-sidebar-border hover:text-sidebar-text"
                        >
                          <PencilIcon />
                        </button>
                        {confirmDeleteId === session.id ? (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              onDelete(session.id);
                              setConfirmDeleteId(null);
                            }}
                            aria-label="Confirm delete"
                            title="Confirm delete"
                            className="flex h-7 w-7 items-center justify-center rounded-full text-danger hover:bg-danger/10"
                          >
                            <CheckIcon />
                          </button>
                        ) : (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setConfirmDeleteId(session.id);
                            }}
                            aria-label="Delete chat"
                            title="Delete"
                            className="flex h-7 w-7 items-center justify-center rounded-full text-sidebar-text-faint hover:bg-sidebar-border hover:text-sidebar-text"
                          >
                            <TrashIcon />
                          </button>
                        )}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div ref={settingsRef} className="relative border-t border-sidebar-border p-2">
        {settingsOpen && (
          <div className="absolute bottom-full left-2 right-2 mb-1 rounded-xl border border-sidebar-border bg-sidebar-input p-1 shadow-lg">
            <div className="px-3 py-2 text-[13px] font-medium text-sidebar-text-faint">Appearance</div>
            <button
              type="button"
              onClick={() => setTheme("dark")}
              className={`flex w-full items-center gap-2.5 rounded-full px-3 py-2 text-left text-[13px] ${
                theme === "dark" ? "bg-sidebar-active text-sidebar-text" : "text-sidebar-text-muted hover:bg-sidebar-hover"
              }`}
            >
              <MoonIcon /> Dark
            </button>
            <button
              type="button"
              onClick={() => setTheme("light")}
              className={`flex w-full items-center gap-2.5 rounded-full px-3 py-2 text-left text-[13px] ${
                theme === "light" ? "bg-sidebar-active text-sidebar-text" : "text-sidebar-text-muted hover:bg-sidebar-hover"
              }`}
            >
              <SunIcon /> Light
            </button>
          </div>
        )}
        <button
          type="button"
          onClick={() => setSettingsOpen((v) => !v)}
          className="flex w-full items-center gap-2.5 rounded-full px-2 py-2 text-left transition-colors hover:bg-sidebar-hover"
        >
          {/* eslint-disable-next-line @next/next/no-img-element -- see the mads-icon.png note above: next/image's optimizer cache ignores in-place file swaps */}
          <img
            src="/avatar.png"
            alt=""
            className="h-7 w-7 shrink-0 rounded-full object-cover"
            style={{ objectPosition: "50% 22%" }}
          />
          <span className="min-w-0 flex-1 truncate text-[13px] font-normal text-sidebar-text">{USER_NAME}</span>
          <GearIcon />
        </button>
      </div>
    </div>
  );
}

export function useSidebarCollapsed(): [boolean, () => void] {
  const [collapsed, setCollapsed] = useState(() => {
    if (typeof window === "undefined") return false;
    try {
      return localStorage.getItem(STORAGE_KEY) === "1";
    } catch {
      return false;
    }
  });

  const toggle = () => {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
      } catch {
        // Not worth surfacing — the toggle still works for this tab.
      }
      return next;
    });
  };

  return [collapsed, toggle];
}

function SidebarIcon() {
  return (
    <svg viewBox="0 0 16 16" width="15" height="15" fill="none">
      <rect x="2" y="2.5" width="12" height="11" rx="2" stroke="currentColor" strokeWidth="1.3" />
      <path d="M6.5 2.5v11" stroke="currentColor" strokeWidth="1.3" />
    </svg>
  );
}

function NewChatIcon() {
  return (
    <svg viewBox="0 0 16 16" width="15" height="15" fill="none">
      <path d="M8 3.5v9M3.5 8h9" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg viewBox="0 0 16 16" width="13" height="13" fill="none" className="shrink-0 text-sidebar-text-faint">
      <circle cx="7" cy="7" r="4.25" stroke="currentColor" strokeWidth="1.3" />
      <path d="M12.5 12.5L10 10" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  );
}

function PencilIcon() {
  return (
    <svg viewBox="0 0 16 16" width="12" height="12" fill="none">
      <path
        d="M11.4 2.6 13.4 4.6M4.3 12.7l.6-2.5 7-7a1.1 1.1 0 0 1 1.6 0l.3.3a1.1 1.1 0 0 1 0 1.6l-7 7-2.5.6Z"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg viewBox="0 0 16 16" width="12" height="12" fill="none">
      <path
        d="M3 4.5h10M6.5 4.5v-1a1 1 0 0 1 1-1h1a1 1 0 0 1 1 1v1M4.5 4.5l.6 8a1 1 0 0 0 1 .9h3.8a1 1 0 0 0 1-.9l.6-8"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg viewBox="0 0 16 16" width="12" height="12" fill="none">
      <path d="M3.5 8.5l2.5 2.5L12.5 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function GearIcon() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" fill="none" className="shrink-0 text-sidebar-text-faint">
      <circle cx="8" cy="8" r="2.2" stroke="currentColor" strokeWidth="1.2" />
      <path
        d="M8 2.2v1.3M8 12.5v1.3M13.8 8h-1.3M3.5 8H2.2M11.8 4.2l-.9.9M5.1 10.9l-.9.9M11.8 11.8l-.9-.9M5.1 5.1l-.9-.9"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinecap="round"
      />
    </svg>
  );
}

function SunIcon() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" fill="none">
      <circle cx="8" cy="8" r="3" stroke="currentColor" strokeWidth="1.3" />
      <path
        d="M8 1.5v1.3M8 13.2v1.3M14.5 8h-1.3M2.8 8H1.5M12.6 3.4l-.9.9M4.3 11.7l-.9.9M12.6 12.6l-.9-.9M4.3 4.3l-.9-.9"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
      />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" fill="none">
      <path
        d="M13.5 9.5a5.8 5.8 0 0 1-7-7 5.8 5.8 0 1 0 7 7Z"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ToolsIcon() {
  return (
    <svg viewBox="0 0 16 16" width="15" height="15" fill="none">
      <path
        d="M9.7 3.3a2.9 2.9 0 0 0-3.8 3.4L2.5 10.1a1.4 1.4 0 0 0 2 2l3.4-3.4a2.9 2.9 0 0 0 3.4-3.8l-1.8 1.8-1.5-.3-.3-1.5Z"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

function ImageIcon() {
  return (
    <svg viewBox="0 0 16 16" width="15" height="15" fill="none">
      <rect x="2" y="2.5" width="12" height="11" rx="1.6" stroke="currentColor" strokeWidth="1.2" />
      <circle cx="6" cy="6.5" r="1.1" stroke="currentColor" strokeWidth="1.1" />
      <path d="M3 11.5l3.3-3.3a1 1 0 0 1 1.4 0L10 10.5M10.8 9.3l.6-.6a1 1 0 0 1 1.4 0l1.2 1.2" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ConnectIcon() {
  return (
    <svg viewBox="0 0 16 16" width="15" height="15" fill="none">
      <path
        d="M6.8 9.2 9.2 6.8M6.3 9.7 4.6 11.4a2 2 0 1 1-2.8-2.8l1.7-1.7M9.7 6.3l1.7-1.7a2 2 0 1 1 2.8 2.8l-1.7 1.7"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinecap="round"
      />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg viewBox="0 0 16 16" width="13" height="13" fill="none">
      <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}
