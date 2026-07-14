# Mads

Mads is a personal AI Chief of Staff — a CLI-based AI operating system built around one core
idea: **one brain, many tools.** Gemini decides what to do and which capability to use; there is
no keyword routing, no multi-agent orchestration, and no hardcoded "if X then call Y" logic
anywhere in the codebase. Every capability — reading a file, searching Gmail, controlling
Spotify, checking battery status, planning your day, recalling something you told ChatGPT a year
ago — is just a function Gemini can choose to call.

Two things sit above the tool layer without breaking that model: **Advanced Planner**, which
gives Mads standing awareness of your active project, tasks, and prompts; and **Adaptive
Intelligence**, which learns durable facts about you from imported conversation history, subject
to your explicit approval before anything is trusted.

## Why this architecture

Most "AI assistant" projects either hardcode intent → action mappings, or reach for multi-agent
frameworks before they're needed. Mads deliberately avoids both:

- **No keyword routing.** Nothing in this codebase inspects the user's message for words like
  `"email"` or `"volume"` to decide what to do. Gemini's function calling makes that decision
  every time, using the natural-language tool descriptions as its only guide.
- **No multi-agent orchestration.** There is one Gemini chat session per run. When a task needs
  several independent lookups (e.g. Research Mode fetching from Context7, GitHub, the web, and
  YouTube at once), those are *concurrent tool calls within the same reasoning turn*
  (`asyncio.gather`), not separate agent instances with their own reasoning loops.
- **Every capability looks the same to the agent.** Whether a tool spawns a real MCP server
  subprocess, calls a REST API directly, or shells out to `osascript`, the agent only ever sees a
  `ToolProvider`: `list_tools()` + `call_tool()`. It has no idea which is which, and doesn't need
  to.
- **Intelligence layers orchestrate, they don't replace.** Advanced Planner and Adaptive
  Intelligence sit *above* the tool layer — they shape what the agent already knows going into a
  conversation (system-prompt context) and expose a few extra tools of their own, but they never
  bypass the same `ToolProvider` interface everything else uses.

## Architecture

```mermaid
flowchart TB
    User(["Sayan"]) --> CLI["cli/main.py — REPL"]
    CLI --> Planner["planner/planner.py — Planner"]
    CLI --> AdaptiveProfile["adaptive/profile.py — AdaptiveProfile"]
    CLI --> Agent["agent/agent.py — Agent"]
    Agent <--> Gemini["Gemini 2.5 (function calling)"]
    Agent --> Manager["mcp_servers/manager.py — MCPManager"]

    Planner -. render_system_context .-> Agent
    AdaptiveProfile -. render_context .-> Agent

    Manager --> Stdio["StdioToolProvider"]
    Manager --> Local["Local ToolProviders"]

    Stdio --> FS["Filesystem MCP<br/>(@modelcontextprotocol/server-filesystem)"]
    Stdio --> Fetch["Fetch MCP<br/>(mcp-server-fetch)"]
    Stdio --> C7["Context7 MCP<br/>(@upstash/context7-mcp)"]
    Stdio --> GH["GitHub MCP<br/>(github-mcp-server, Go binary)"]

    Local --> GW["Google Workspace<br/>Gmail · Calendar · Drive · Docs · Sheets"]
    Local --> YT["YouTube<br/>Data API v3"]
    Local --> SP["Spotify<br/>Web API"]
    Local --> SR["Search<br/>SerpApi"]
    Local --> MP["Maps<br/>Google Maps API"]
    Local --> DI["Document Intelligence<br/>PDF · DOCX · XLSX · PPTX"]
    Local --> IMG["Image<br/>Pollinations"]
    Local --> SYS["System Tool<br/>macOS native control"]
    Local --> MEM["Memory Engine<br/>SQLite"]
    Local --> PLN["Planner Tools<br/>projects · tasks · prompts · plans"]
    Local --> ADP["Adaptive Tools<br/>approval queue · learned profile"]

    GW -.OAuth.-> OAuthMgr["auth/oauth_manager.py<br/>OAuthManager + adapters"]
    SP -.OAuth.-> OAuthMgr
    OAuthMgr --> TokenStore[("~/.mads/auth/*.enc<br/>Fernet-encrypted")]

    MEM --> MemDB[("~/.mads/memory.sqlite3")]
    PLN --> PlanFiles[("~/.mads/projects/&lt;slug&gt;/*.json")]
    ADP --> AdaptiveFiles[("~/.mads/adaptive/*.json")]

    style Gemini fill:#4285f4,color:#fff
    style Agent fill:#1a73e8,color:#fff
    style Manager fill:#34a853,color:#fff
    style Planner fill:#fbbc04,color:#000
    style AdaptiveProfile fill:#ea4335,color:#fff
```

**The agent never branches on tool identity.** `Agent.send()` sends a message, and for every
function call Gemini requests in that turn, dispatches to `MCPManager.call_tool(name, args)` —
that's the entire routing logic. `MCPManager` resolves `name` to whichever `ToolProvider`
registered it and returns the result. Independent calls in the same turn run concurrently.

**Planner and AdaptiveProfile are not `ToolProvider`s themselves.** They're plain Python objects
`cli/main.py` constructs once per session, used to render two blocks of system-prompt context
(active project + plan, and approved learned facts) before the Agent is even built. Each also
owns a *thin* `ToolProvider` (`PlannerProvider`, `AdaptiveProvider`) so Gemini can still query or
mutate them mid-conversation — but the underlying objects are fully usable, testable, and
inspectable with zero Gemini or MCP involvement.

## Request lifecycle

```mermaid
sequenceDiagram
    participant U as Sayan
    participant A as Agent
    participant G as Gemini
    participant M as MCPManager
    participant T as ToolProvider(s)

    U->>A: "what's on my calendar today, and check for any GitHub PR reviews"
    A->>G: send_message(prompt + tool declarations)
    G-->>A: function_calls: [list_events(), search_pull_requests()]
    par concurrent tool calls
        A->>M: call_tool("list_events", {...})
        M->>T: Google Workspace provider
        T-->>M: {"events": [...]}
        M-->>A: ToolCallResult
    and
        A->>M: call_tool("search_pull_requests", {...})
        M->>T: GitHub MCP provider
        T-->>M: {"pull_requests": [...]}
        M-->>A: ToolCallResult
    end
    A->>G: send_message(both tool results)
    G-->>A: final natural-language reply
    A-->>U: "You've got 2 events today... and 3 PRs waiting on your review..."
```

## Advanced Planner

Mads knows which project you're working on the way a shell knows your current directory — you
don't tell it, it detects it.

```mermaid
flowchart TD
    Start(["Mads starts"]) --> Detect["Planner.resolve_startup_project(cwd)"]
    Detect --> Walk{"Walk up from cwd:<br/>.git / pyproject.toml / package.json /<br/>go.mod / Cargo.toml / ... found?"}

    Walk -- "no marker found" --> LastActive{"Last active<br/>project on record?"}
    LastActive -- no --> NoProject(["No active project —<br/>global FILESYSTEM_ROOT"])
    LastActive -- yes --> AskResume["'Good morning.<br/>Last active project: X. Continue? [Y/n]'"]
    AskResume -- Y --> ActivateLast["set_active(X)"]
    AskResume -- n --> NoProject

    Walk -- "marker found" --> Known{"Folder already<br/>registered?"}
    Known -- yes --> SilentActivate["set_active(project) — no prompt"]
    Known -- no --> Offer["'I detected a new project:<br/>Name / Workspace / GitHub.<br/>Register it? [Y/n]'"]
    Offer -- Y --> AutoDetect["Name + GitHub repo<br/>auto-detected from folder + git remote"]
    AutoDetect --> Register["register_workspace() → set_active()"]
    Offer -- n --> NoProject

    SilentActivate --> Session
    ActivateLast --> Session
    Register --> Session["_build_session():<br/>filesystem MCP scoped to project folder,<br/>render_system_context() → Agent"]
    NoProject --> Session

    style Session fill:#1a73e8,color:#fff
    style SilentActivate fill:#34a853,color:#fff
    style Register fill:#34a853,color:#fff
```

- **Workspace discovery, not manual registration.** Launch Mads from inside any folder with a
  `.git`, `pyproject.toml`, `package.json`, `go.mod`, `Cargo.toml`, or similar marker, and
  `Planner.resolve_startup_project()` either silently activates it (if already known) or offers
  to register it (name and GitHub repo auto-detected from the folder and its git remote — never
  asked for).
- **Project-scoped everything.** Once a project is active, the filesystem MCP server, tasks, and
  prompts are all scoped to it. Switching projects (`use project <name>`) tears down and rebuilds
  the whole tool session around the new scope.
- **Tasks** (`planner/task_manager.py`): priority, status (open/in-progress/blocked/done), due
  dates, tags — stored per-project at `~/.mads/projects/<slug>/tasks.json`.
- **Prompt library** (`planner/prompt_library.py`): reusable prompt templates as Markdown +
  frontmatter, either global (`~/.mads/prompts/global/`) or project-scoped
  (`~/.mads/projects/<slug>/prompts/`).
- **Planning Engine** (`planner/planning_engine.py`): rule-based (no extra LLM call) — ranks open
  tasks by overdue → due-today → priority → recency, and surfaces a suggested prompt and next
  task. Deliberately deterministic and free; this is the seam future adaptive prioritization
  would plug into without changing its public surface.
- **Dashboard** (`planner/dashboard.py`): project identity, task counts and progress, current git
  branch, recent commits, recent documents, recommended next task — all computed fresh on each
  call, never cached.

Try it: `dashboard` and `plan` as REPL commands, or just ask Mads directly — "what should I work
on today?" reaches the same Planning Engine through the `daily_plan` tool.

## Adaptive Intelligence

Mads can learn who you are and how you work from a ChatGPT export — but nothing it extracts is
trusted until you say so.

```mermaid
flowchart TD
    Import(["import chatgpt &lt;path&gt;<br/>(CLI-only — not a Gemini tool)"]) --> Read["export_reader.py<br/>walk mapping tree from current_node → linear text"]
    Read --> Ledger{"Ledger:<br/>already processed<br/>(id + content hash)?"}
    Ledger -- yes --> Skip(["Skipped — free"])
    Ledger -- no --> Gate{"gatekeeper.py<br/>cheap floor:<br/>&lt; 3 messages or too short?"}

    Gate -- yes --> MarkGated["ledger: 'gated'"]
    MarkGated --> Skip

    Gate -- no --> Classify["classifier.py<br/>batched Gemini yes/no (~20/call, concurrent):<br/>worth learning?"]
    Classify -- no --> MarkNotWorth["ledger: 'not_worth_learning'"]
    MarkNotWorth --> Skip

    Classify -- yes --> Compress["compressor.py<br/>strip filler, collapse code blocks,<br/>edge-truncate to ~1500 chars"]
    Compress --> Extract["extractor.py<br/>batched Gemini extraction:<br/>preference · decision · workflow · constraint · identity"]
    Extract --> Score["scorer.py<br/>cluster duplicates, score confidence<br/>(recurrence, consistency, contradiction, recency)"]
    Score --> Enqueue["profile.py: enqueue()<br/>→ pending.json"]
    Enqueue --> MarkExtracted["ledger: 'extracted'"]

    Enqueue --> Review["You: list_pending_candidates"]
    Review --> Decide{"approve_candidate<br/>or reject_candidate"}
    Decide -- approve --> Profile["profile.json<br/>(chmod 0600, atomic write)"]
    Decide -- reject --> Discarded(["Discarded — never stored"])

    Profile --> Context["render_context()<br/>→ system prompt, next session"]
    Profile --> Search["search_memory<br/>merged with memory.sqlite3"]

    style Extract fill:#4285f4,color:#fff
    style Classify fill:#4285f4,color:#fff
    style Profile fill:#34a853,color:#fff
    style Discarded fill:#ea4335,color:#fff
```

**Pipeline** (`adaptive/pipeline.py`), run via the CLI-only `import chatgpt <path>` command
(deliberately *not* a tool Gemini can trigger on its own — it's a slow, real-cost bulk job):

1. **Read** (`export_reader.py`) — walks each conversation's `mapping` tree from `current_node`
   back to root, reconstructing the linear conversation as currently visible in ChatGPT's UI.
2. **Ledger check** (`ledger.py`) — skips conversations already processed (by id + content hash),
   so re-running import against the same export after the first pass costs nothing.
3. **Gate** (`gatekeeper.py`) — a cheap, non-LLM floor that drops trivially short/empty
   conversations before spending any API call on them.
4. **Classify** (`classifier.py`) — batched Gemini calls (~20 conversations/call, run
   concurrently) ask a plain yes/no: does this conversation contain anything durable worth
   learning? Replaces keyword regex, which misses implicit signal.
5. **Compress** (`compressor.py`) — strips filler/greetings, collapses code blocks, edge-truncates
   long conversations to ~1500 characters before the more expensive extraction call.
6. **Extract** (`extractor.py`) — batched extraction into five categories: **preference**,
   **decision**, **workflow**, **constraint**, and **identity** (name, institution, contact info —
   always extracted when present, even from a one-off task).
7. **Score** (`scorer.py`) — clusters near-duplicate candidates (a fact restated five different
   ways becomes one entry), scores confidence from recurrence, consistency, detected
   contradictions (penalized), and a slight recency boost.
8. **Approval queue** (`profile.py`) — every scored candidate lands in a pending queue. **Nothing
   reaches the Adaptive Profile without explicit approval** — `list_pending_candidates`,
   `approve_candidate`, `reject_candidate` are ordinary chat tools.

Once approved, a fact is folded into `AdaptiveProfile.render_context()`, which reaches the system
prompt the same way Planner's project context does — and into `search_memory`, which searches
*both* `memory.sqlite3` (things you told Mads directly) and the Adaptive Profile (things learned
from imported history) as one merged, relevance-ranked result set.

Storage lives at `~/.mads/adaptive/`: `pending.json` (awaiting review), `profile.json` (approved,
`chmod 0600`), `ledger.json` (import bookkeeping). All writes go through an atomic
temp-file-then-`os.replace()` path — concurrent tool calls in the same turn (Gemini can fire
several `approve_candidate` calls at once) can no longer corrupt these files.

## What's inside

| Capability | Backed by | Tools |
|---|---|---|
| **Filesystem** | Official `@modelcontextprotocol/server-filesystem` (npx, stdio MCP) — multi-root: active project folder + home directory | — |
| **Fetch** | Official `mcp-server-fetch` (uvx, stdio MCP) | — |
| **Context7** | Official `@upstash/context7-mcp` (npx, stdio MCP) | — |
| **GitHub** | Official `github-mcp-server` Go binary, read-only mode (stdio MCP) | — |
| **Google Workspace** | Direct Gmail/Calendar/Drive/Docs/Sheets REST APIs (OAuth) — official per-app MCP servers exist but can't send/write or cover Docs/Sheets, so this calls the APIs directly | 20 |
| **YouTube** | Direct YouTube Data API v3 (API key) — the community MCP server for this is broken against current SDK versions | 4 |
| **Spotify** | Direct Spotify Web API (OAuth) | 2 |
| **Search** | SerpApi (API key) | 1 |
| **Maps** | Google Maps API (API key) | 3 |
| **Document Intelligence** | PyMuPDF, python-docx, openpyxl, reportlab, python-pptx — local only, no MCP | 7 |
| **Image** | Pollinations — local only, no MCP | 1 |
| **System Tool** | `osascript`, `psutil`, native macOS commands — local only, no MCP | 13 |
| **Memory Engine** | SQLite (`~/.mads/memory.sqlite3`) — preference/project/decision/person/identity | 5 |
| **Planner** | `planner/` — projects, tasks, prompts, daily plan, dashboard | 14 |
| **Adaptive Intelligence** | `adaptive/` — approval queue + learned profile (import itself is CLI-only, not a tool) | 4 |

(External stdio MCP servers don't expose a fixed tool count from this codebase — it's whatever
that server's own release defines.)

Where an official MCP server exists *and* covers what's needed (Filesystem, Fetch, Context7,
GitHub), Mads uses it. Where the official option is missing, broken, or too narrow (Google
Workspace write operations, YouTube transcripts, Spotify, Search, Maps), Mads calls the real API
directly instead — but exposes it through the exact same `ToolProvider` interface, so the agent
can't tell the difference.

## Safety model

- **Filesystem-scoped to multiple roots.** Filesystem, Document Intelligence, and destructive
  System tools are confined to `Settings.allowed_roots` — the active project's folder (or
  `FILESYSTEM_ROOT` if none is active) **and** your home directory, always. Paths outside both are
  rejected before any read/write happens. This is a single source of truth
  (`config/settings.py: allowed_roots` / `is_path_allowed`) shared by all three tool surfaces.
- **Destructive system operations require confirmation** (`shutdown`, `restart`, `empty_trash`,
  `delete_files`, `terminate_process`). Each takes a `confirmed: bool` parameter; the first call
  always returns `requires_confirmation: true` with no side effect. Gemini surfaces this to you in
  plain conversation, you confirm in your own words, and only then does Gemini re-call with
  `confirmed=true`. No blocking prompts inside a tool call, no special-cased agent logic — it's
  just another turn of ordinary function calling.
- **OAuth tokens are encrypted at rest** under `~/.mads/auth/<provider>.enc` (Fernet, key derived
  from `OAUTH_TOKEN_ENCRYPTION_KEY`), refreshed silently, and never logged or printed.
- **Adaptive Intelligence never learns automatically.** Every extracted candidate — preference,
  decision, workflow, constraint, or identity fact — sits in a pending queue until you explicitly
  approve it. The import pipeline itself is a CLI-only command, not something Gemini can trigger
  mid-conversation. Approved-fact and pending-queue files are `chmod 0600` and written atomically.
- **Raw imported conversations never reach the model at runtime.** They're read once during
  import to produce candidates, then discarded from the active context — only the structured,
  approved Adaptive Profile is ever injected into the system prompt.

## Getting started

```bash
git clone <this-repo>
cd mads
cp .env.example .env   # fill in GEMINI_API_KEY at minimum; other integrations are optional
uv sync
uv run mads
```

See `.env.example` for every integration's required variables — each one is optional except
`GEMINI_API_KEY`; Mads simply shows `✗` in its startup banner for anything unconfigured and skips
it. GitHub also needs its Go binary built once (`go install
github.com/github/github-mcp-server/cmd/github-mcp-server@latest`), and Google
Workspace/Spotify need one-time browser OAuth consent on first use.

Once running, launch it from inside a project folder and Mads will offer to register it
automatically — see [Advanced Planner](#advanced-planner). To import ChatGPT history, run `import
chatgpt <path-to-export-folder>` from the REPL — see [Adaptive
Intelligence](#adaptive-intelligence).

## Project layout

```
mads/
├── agent/                    # The single agent: Gemini session, tool-call loop, prompts
├── auth/                     # Shared OAuthManager + per-provider adapters (Google, Spotify)
├── cli/                      # REPL entrypoint — session assembly, startup flow, commands
├── config/                   # Typed Settings, loaded once from environment
├── mcp_servers/
│   ├── manager.py            # ToolProvider protocol + MCPManager
│   └── servers/               # One module/subpackage per capability
├── memory/                   # SQLite-backed memory engine + static profile
├── planner/                  # Advanced Planner: projects, tasks, prompts, planning, dashboard
├── adaptive/                 # Adaptive Intelligence: ChatGPT import pipeline + approval queue
└── pyproject.toml
```

## Where things are stored

Everything Mads persists lives under `~/.mads/`:

```
~/.mads/
├── memory.sqlite3            # Direct memory: preference/project/decision/person/identity
├── active_project             # Pointer to the currently active project slug
├── auth/*.enc                 # Fernet-encrypted OAuth tokens
├── prompts/global/*.md        # Global prompt library
├── projects/<slug>/
│   ├── project.json           # Name, GitHub repo, folder, drive folder
│   ├── tasks.json              # Project-scoped tasks
│   └── prompts/*.md            # Project-scoped prompts
└── adaptive/
    ├── pending.json            # Candidates awaiting approval
    ├── profile.json             # Approved facts — the only thing the model ever sees
    └── ledger.json               # Import bookkeeping (id + content hash) for incremental imports
```

Note: Please add your personal information to `memory/profile.md`. This will help Mads
personalize its responses and retain relevant long-term context.
