"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { API_BASE } from "@/lib/useChat";
import { toast } from "@/lib/toast";

// Connectors with no cached OAuth token yet only ever connect via an
// explicit click here — see server/app.py's /api/connectors/{id}/connect
// and agent/session.py's COMMERCE_CONNECTORS for why these specifically
// (unlike every other service on this page) are never auto-connected at
// server startup.
const CONNECTABLE_IDS = new Set(["swiggy", "zepto", "groww", "zomato"]);

interface ToolEntry {
  id: string;
  name: string;
  description: string;
  /** Path under /logos for a real third-party brand mark, fetched from
   * Simple Icons (CC0, simpleicons.org) — omit for a built-in Mads
   * capability, which gets one of the line icons below instead. */
  logo?: string;
  /** Tile background behind the logo — white works for every brand mark
   * we use here since each SVG already carries its own brand color. */
  tileBg?: string;
  Icon?: (props: { className?: string; style?: React.CSSProperties }) => React.JSX.Element;
  accent?: string;
}

const SERVICES: ToolEntry[] = [
  { id: "github", name: "GitHub", description: "Repos, issues, and pull requests", logo: "/logos/github.svg", tileBg: "#ffffff" },
  {
    id: "google_workspace",
    name: "Google Workspace",
    description: "Gmail, Calendar, Docs, Sheets, Drive",
    logo: "/logos/google.svg",
    tileBg: "#ffffff",
  },
  { id: "youtube", name: "YouTube", description: "Search and read video details", logo: "/logos/youtube.svg", tileBg: "#ffffff" },
  { id: "spotify", name: "Spotify", description: "Search and control playback", logo: "/logos/spotify.svg", tileBg: "#ffffff" },
  { id: "maps", name: "Google Maps", description: "Places and directions", logo: "/logos/googlemaps.svg", tileBg: "#ffffff" },
  { id: "swiggy", name: "Swiggy", description: "Order food — invite-only access", logo: "/logos/swiggy.svg", tileBg: "#ffffff" },
  { id: "zepto", name: "Zepto", description: "Quick-commerce grocery delivery", logo: "/logos/zepto.jpg", tileBg: "#ffffff" },
  { id: "groww", name: "Groww", description: "Stocks, F&O, and real trades", logo: "/logos/groww.png", tileBg: "#ffffff" },
  { id: "zomato", name: "Zomato", description: "Order food — approval-gated access", logo: "/logos/zomato.svg", tileBg: "#ffffff" },
];

const BUILTIN: ToolEntry[] = [
  { id: "filesystem", name: "Filesystem", description: "Read and edit files on this Mac", Icon: FolderIcon, accent: "#8ab4f8" },
  { id: "fetch", name: "Fetch", description: "Load and read web pages", Icon: GlobeIcon, accent: "#5fc98d" },
  { id: "context7", name: "Context7", description: "Up-to-date library and API docs", Icon: BookIcon, accent: "#e0a65c" },
  { id: "search", name: "Web Search", description: "General web search", Icon: SearchToolIcon, accent: "#8ab4f8" },
  { id: "astrology", name: "Astrology", description: "Charts and predictions", Icon: StarIcon, accent: "#c89bf0" },
  { id: "memory", name: "Memory", description: "Recalls things Mads has learned about you", Icon: BrainIcon, accent: "#f28b82" },
  { id: "system", name: "System", description: "Local system info and commands", Icon: TerminalIcon, accent: "#9aa0a6" },
  { id: "image", name: "Image", description: "Generate and edit images", Icon: PictureIcon, accent: "#c89bf0" },
  { id: "planner", name: "Planner", description: "Projects and active-workspace tracking", Icon: ChecklistIcon, accent: "#5fc98d" },
  { id: "adaptive", name: "Adaptive", description: "Learns your preferences over time", Icon: SparkleIcon, accent: "#e0a65c" },
  { id: "browser_control", name: "Browser Control", description: "Drives your Chrome via the Mads extension", Icon: CursorIcon, accent: "#8ab4f8" },
  { id: "excel_control", name: "Excel Control", description: "Reads and writes the open workbook", Icon: GridIcon, accent: "#5fc98d" },
];

export default function ToolsPage() {
  const [connected, setConnected] = useState<string[] | null>(null);
  const [error, setError] = useState(false);
  const [query, setQuery] = useState("");
  const [connectingId, setConnectingId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/status`);
        if (!res.ok) throw new Error();
        const data = await res.json();
        if (!cancelled) setConnected(data.connected_servers ?? []);
      } catch {
        if (!cancelled) setError(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const isConnected = (id: string) => connected?.includes(id) ?? false;

  // Can take up to ~20s (mcp_servers/manager.py's _CONNECT_TIMEOUT_SECONDS)
  // since a service with no cached OAuth token yet opens a real browser
  // login right then — the button shows a spinner for the whole wait
  // rather than looking frozen.
  const handleConnect = useCallback(async (id: string) => {
    setConnectingId(id);
    try {
      const res = await fetch(`${API_BASE}/api/connectors/${id}/connect`, { method: "POST" });
      const data = await res.json();
      if (data.connected) {
        setConnected((prev) => (prev ? [...new Set([...prev, id])] : [id]));
      } else {
        toast(data.error || `Couldn't connect — check the backend's logs for ${id}.`);
      }
    } catch {
      toast("Couldn't reach Mads to connect that service.");
    } finally {
      setConnectingId(null);
    }
  }, []);

  const q = query.trim().toLowerCase();
  const matches = (t: ToolEntry) => !q || t.name.toLowerCase().includes(q) || t.description.toLowerCase().includes(q);
  const visibleServices = useMemo(() => SERVICES.filter(matches), [q]);
  const visibleBuiltin = useMemo(() => BUILTIN.filter(matches), [q]);

  const installedRow = [...SERVICES, ...BUILTIN].filter((t) => isConnected(t.id));

  return (
    <div className="h-full w-full overflow-y-auto bg-bg">
      <div className="mx-auto w-full max-w-3xl px-5 py-8 sm:px-8">
        <Link
          href="/"
          className="mb-6 inline-flex items-center gap-1.5 text-[13px] text-text-muted transition-colors hover:text-text"
        >
          <BackIcon />
          Back to chat
        </Link>

        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-[28px] font-semibold text-text">Tools</h1>
            <p className="mt-1 text-[14px] text-text-muted">See what Mads can do for you.</p>
          </div>
          <div className="flex items-center gap-2 rounded-full border border-border bg-surface px-3.5 py-2">
            <SearchIcon />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search tools"
              className="w-40 bg-transparent text-[13px] text-text placeholder:text-text-faint focus:outline-none sm:w-52"
            />
          </div>
        </div>

        {error && (
          <p className="mt-6 text-[13px] text-danger">Couldn&apos;t reach Mads to check what&apos;s connected.</p>
        )}

        {!q && installedRow.length > 0 && (
          <section className="mt-8">
            <h2 className="text-[13px] font-medium text-text-muted">Installed</h2>
            <div className="mt-3 flex flex-wrap gap-3">
              {installedRow.map((t) => (
                <div
                  key={t.id}
                  title={t.name}
                  className="flex h-11 w-11 items-center justify-center rounded-xl"
                  style={{ backgroundColor: t.logo ? t.tileBg : `${t.accent}26` }}
                >
                  {t.logo ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={t.logo} alt={t.name} className="h-6 w-6" />
                  ) : (
                    t.Icon && <t.Icon className="h-5 w-5" style={{ color: t.accent } as React.CSSProperties} />
                  )}
                </div>
              ))}
            </div>
          </section>
        )}

        <section className="mt-8">
          <h2 className="text-[13px] font-medium text-text-muted">Connected services</h2>
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
            {visibleServices.map((t) => (
              <ToolCard
                key={t.id}
                tool={t}
                connected={isConnected(t.id)}
                connecting={connectingId === t.id}
                onConnect={handleConnect}
              />
            ))}
          </div>
        </section>

        <section className="mt-8 pb-10">
          <h2 className="text-[13px] font-medium text-text-muted">Built-in capabilities</h2>
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
            {visibleBuiltin.map((t) => (
              <ToolCard key={t.id} tool={t} connected={isConnected(t.id)} />
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

function ToolCard({
  tool,
  connected,
  connecting,
  onConnect,
}: {
  tool: ToolEntry;
  connected: boolean;
  connecting?: boolean;
  onConnect?: (id: string) => void;
}) {
  const Icon = tool.Icon;
  const showConnectButton = !connected && CONNECTABLE_IDS.has(tool.id) && onConnect;

  return (
    <div className="flex items-center gap-3.5 rounded-2xl border border-border bg-surface px-4 py-3.5">
      <div
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl"
        style={{ backgroundColor: tool.logo ? tool.tileBg : `${tool.accent}26` }}
      >
        {tool.logo ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={tool.logo} alt={tool.name} className="h-5 w-5" />
        ) : (
          Icon && <Icon className="h-5 w-5" style={{ color: tool.accent } as React.CSSProperties} />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[14px] font-medium text-text">{tool.name}</p>
        <p className="truncate text-[12px] text-text-muted">{tool.description}</p>
      </div>
      {showConnectButton ? (
        <button
          type="button"
          onClick={() => onConnect(tool.id)}
          disabled={connecting}
          className="flex shrink-0 items-center gap-1.5 rounded-full bg-text px-3 py-1.5 text-[11px] font-medium text-bg transition-opacity hover:opacity-90 disabled:opacity-60"
        >
          {connecting && <SpinnerIcon />}
          {connecting ? "Connecting…" : "Connect"}
        </button>
      ) : (
        <span
          className={`flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium ${
            connected ? "bg-green-500/15 text-green-500" : "bg-text-faint/15 text-text-faint"
          }`}
        >
          <span className={`h-1.5 w-1.5 rounded-full ${connected ? "bg-green-500" : "bg-text-faint"}`} />
          {connected ? "Connected" : "Not connected"}
        </span>
      )}
    </div>
  );
}

function SpinnerIcon() {
  return (
    <svg viewBox="0 0 16 16" width="11" height="11" className="animate-spin" fill="none">
      <circle cx="8" cy="8" r="6" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2" />
      <path d="M14 8a6 6 0 0 0-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function BackIcon() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" fill="none">
      <path d="M10 12.5L5.5 8l4.5-4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg viewBox="0 0 16 16" width="13" height="13" fill="none" className="shrink-0 text-text-faint">
      <circle cx="7" cy="7" r="4.25" stroke="currentColor" strokeWidth="1.3" />
      <path d="M12.5 12.5L10 10" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  );
}

function FolderIcon({ className, style }: { className?: string; style?: React.CSSProperties }) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" className={className} style={style} fill="none">
      <path d="M3 6.5a1 1 0 0 1 1-1h4.5l2 2H20a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1Z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
    </svg>
  );
}

function GlobeIcon({ className, style }: { className?: string; style?: React.CSSProperties }) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" className={className} style={style} fill="none">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.6" />
      <path d="M3 12h18M12 3c2.5 2.5 2.5 15.5 0 18M12 3c-2.5 2.5-2.5 15.5 0 18" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
}

function BookIcon({ className, style }: { className?: string; style?: React.CSSProperties }) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" className={className} style={style} fill="none">
      <path d="M4 4.5h7a2 2 0 0 1 2 2V20a1.5 1.5 0 0 0-1.5-1.5H4ZM20 4.5h-7a2 2 0 0 0-2 2V20a1.5 1.5 0 0 1 1.5-1.5H20Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}

function SearchToolIcon({ className, style }: { className?: string; style?: React.CSSProperties }) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" className={className} style={style} fill="none">
      <circle cx="10.5" cy="10.5" r="6.5" stroke="currentColor" strokeWidth="1.6" />
      <path d="M19 19l-4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function StarIcon({ className, style }: { className?: string; style?: React.CSSProperties }) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" className={className} style={style} fill="currentColor">
      <path d="M12 2.5l2.6 6 6.4.6-4.8 4.3 1.4 6.2L12 16.7 6.4 19.6l1.4-6.2-4.8-4.3 6.4-.6Z" />
    </svg>
  );
}

function BrainIcon({ className, style }: { className?: string; style?: React.CSSProperties }) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" className={className} style={style} fill="none">
      <path
        d="M9 4.5a2.8 2.8 0 0 0-2.8 2.8 2.6 2.6 0 0 0-1.7 4.3A2.8 2.8 0 0 0 6 16.5a2.8 2.8 0 0 0 3 2.8V7.3A2.8 2.8 0 0 0 9 4.5ZM15 4.5a2.8 2.8 0 0 1 2.8 2.8 2.6 2.6 0 0 1 1.7 4.3 2.8 2.8 0 0 1-1.5 5 2.8 2.8 0 0 1-3 2.7V7.3a2.8 2.8 0 0 1 0-2.8Z"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function TerminalIcon({ className, style }: { className?: string; style?: React.CSSProperties }) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" className={className} style={style} fill="none">
      <rect x="3" y="4" width="18" height="16" rx="2" stroke="currentColor" strokeWidth="1.6" />
      <path d="M7 9.5l3 2.5-3 2.5M12.5 15h4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function PictureIcon({ className, style }: { className?: string; style?: React.CSSProperties }) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" className={className} style={style} fill="none">
      <rect x="3" y="4" width="18" height="16" rx="2" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="9" cy="10" r="1.8" stroke="currentColor" strokeWidth="1.4" />
      <path d="M4 18l5.5-5.5a1.5 1.5 0 0 1 2.1 0L16 16.9l1.2-1.2a1.5 1.5 0 0 1 2.1 0L21 17.4" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
}

function ChecklistIcon({ className, style }: { className?: string; style?: React.CSSProperties }) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" className={className} style={style} fill="none">
      <path d="M4.5 6.5l1.5 1.5 2.5-2.5M4.5 13.5l1.5 1.5 2.5-2.5M4.5 20.5l1.5 1.5 2.5-2.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M12 7h8M12 14h8M12 21h8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function SparkleIcon({ className, style }: { className?: string; style?: React.CSSProperties }) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" className={className} style={style} fill="currentColor">
      <path d="M12 2l1.8 6.2L20 10l-6.2 1.8L12 18l-1.8-6.2L4 10l6.2-1.8Z" />
    </svg>
  );
}

function CursorIcon({ className, style }: { className?: string; style?: React.CSSProperties }) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" className={className} style={style} fill="none">
      <path d="M5 3.5l5.5 15 2-6.2 6.2-2Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}

function GridIcon({ className, style }: { className?: string; style?: React.CSSProperties }) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" className={className} style={style} fill="none">
      <rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" strokeWidth="1.6" />
      <path d="M3 9h18M3 15h18M9 3v18M15 3v18" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  );
}
