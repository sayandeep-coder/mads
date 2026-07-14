from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

from adaptive.pipeline import run_import
from adaptive.profile import AdaptiveProfile
from adaptive.provider import AdaptiveProvider
from agent.agent import Agent
from agent.research_prompt import build_research_prompt
from config.settings import Settings, get_settings
from mcp_servers.manager import MCPManager, StdioToolProvider, ToolProvider
from mcp_servers.servers import context7 as context7_server
from mcp_servers.servers import fetch as fetch_server
from mcp_servers.servers import filesystem as filesystem_server
from mcp_servers.servers import github as github_server
from mcp_servers.servers import maps as maps_server
from mcp_servers.servers import search as search_server
from mcp_servers.servers import spotify as spotify_server
from mcp_servers.servers import youtube as youtube_server
from mcp_servers.servers.document_intelligence import DocumentIntelligenceProvider
from mcp_servers.servers.google_workspace import GoogleWorkspaceProvider
from mcp_servers.servers.image import ImageProvider
from mcp_servers.servers.system import SystemProvider
from memory.provider import MemoryProvider
from memory.recall import build_recall_summary
from planner.models import Project
from planner.planner import Planner
from planner.provider import PlannerProvider

console = Console()

_HELP_TEXT = """\
Commands:
  exit, quit              Leave Mads
  clear                   Clear the screen
  help                    Show this message
  research <topic>        Deep-dive research using Context7, GitHub, Fetch, and \
YouTube together, synthesized into an executive report
  create project <name>   Register the current (or a chosen) folder as a project — \
GitHub repo is auto-detected from git remote, never asked for
  use project <name>      Switch the active project
  switch project <name>   Same as 'use project'
  dashboard                Show the active project's dashboard
  plan                     Show today's plan for the active project
  import chatgpt <path>    Import a ChatGPT export folder: extracts candidate \
preferences/decisions/workflows/constraints for your approval (list_pending_candidates, \
approve_candidate, reject_candidate). Never auto-learns anything; makes real \
Gemini API calls and can take a few minutes for a large export.

Projects are normally detected automatically: launch Mads from inside a \
git/pyproject/package.json/etc. workspace and it activates (or offers to \
register) that project with no command needed.
"""


def _build_providers(
    settings: Settings, planner: Planner, adaptive_profile: AdaptiveProfile, on_project_switch
) -> list[ToolProvider]:
    providers: list[ToolProvider] = [
        StdioToolProvider("filesystem", filesystem_server.build_server_params(settings)),
        StdioToolProvider("fetch", fetch_server.build_server_params(settings)),
        StdioToolProvider("context7", context7_server.build_server_params(settings)),
    ]
    if github_server.is_available(settings):
        providers.append(StdioToolProvider("github", github_server.build_server_params(settings)))
    if GoogleWorkspaceProvider.is_available(settings):
        providers.append(GoogleWorkspaceProvider(settings))
    if youtube_server.YouTubeProvider.is_available(settings):
        providers.append(youtube_server.YouTubeProvider(settings))
    if spotify_server.SpotifyProvider.is_available(settings):
        providers.append(spotify_server.SpotifyProvider(settings))
    if search_server.SearchProvider.is_available(settings):
        providers.append(search_server.SearchProvider(settings))
    if maps_server.MapsProvider.is_available(settings):
        providers.append(maps_server.MapsProvider(settings))
    providers.append(DocumentIntelligenceProvider(settings))
    providers.append(MemoryProvider(settings))
    providers.append(SystemProvider(settings))
    providers.append(ImageProvider(settings))
    providers.append(PlannerProvider(planner, settings, on_switch=on_project_switch))
    providers.append(AdaptiveProvider(adaptive_profile, settings))
    return providers


_KNOWN_SERVER_NAMES = [
    "filesystem",
    "fetch",
    "context7",
    "github",
    "google_workspace",
    "youtube",
    "spotify",
    "search",
    "maps",
    "document_intelligence",
    "memory",
    "system",
    "image",
    "planner",
    "adaptive",
]


def _configure_logging(log_level: str) -> None:
    logging.basicConfig(level=log_level)
    if log_level != "DEBUG":
        for noisy in ("httpx", "google_genai", "googleapiclient.discovery_cache", "mcp"):
            logging.getLogger(noisy).setLevel(logging.WARNING)


def _settings_for_project(base_settings: Settings, project: Project | None) -> Settings:
    """Scope filesystem_root to the active project's folder, if it has one."""
    if project is not None and project.folder_path is not None:
        return base_settings.with_filesystem_root(project.folder_path)
    return base_settings


@dataclass
class Session:
    """Everything that gets torn down and rebuilt when the active project changes."""

    settings: Settings
    mcp_manager: MCPManager
    agent: Agent


async def _build_session(
    base_settings: Settings, planner: Planner, adaptive_profile: AdaptiveProfile, cwd: Path
) -> Session:
    """(Re)build the live session around whatever Planner currently reports
    as the active project. Called once at startup and again on every
    project switch — a full MCP reconnect, since the filesystem server's
    allowed root and the system prompt both need to follow the switch.
    """
    session_context = planner.start_session(cwd)
    active_project = session_context.active_project.project if session_context.active_project else None
    settings = _settings_for_project(base_settings, active_project)

    mcp_manager = MCPManager()

    async def on_project_switch(new_project: Project) -> None:
        # Tool-call side effect only sets state on disk; the actual live
        # reconnect happens in the REPL loop once it sees the switch below.
        pass

    providers = _build_providers(settings, planner, adaptive_profile, on_project_switch)
    await mcp_manager.connect(providers)

    memory_context = build_recall_summary()
    project_context = planner.render_system_context()
    adaptive_context = adaptive_profile.render_context()
    agent = Agent(
        settings=settings,
        mcp_manager=mcp_manager,
        memory_context=memory_context,
        project_context=project_context,
        adaptive_context=adaptive_context,
    )

    return Session(settings=settings, mcp_manager=mcp_manager, agent=agent)


def _print_banner(session: Session, planner: Planner) -> None:
    console.print("\n[bold cyan]Mads v2[/bold cyan]\n")
    console.print("Connected:")
    connected = set(session.mcp_manager.connected_servers)
    for name in _KNOWN_SERVER_NAMES:
        mark = "[green]✓[/green]" if name in connected else "[red]✗[/red]"
        console.print(f"{mark} {name.capitalize()}")

    active_project = planner.projects.get_active()
    if active_project is not None:
        plan = planner.daily_plan()

        console.print(f"\n[bold]✓ Active Project[/bold]  {active_project.name}")
        if active_project.github_repo:
            console.print(f"  Repository: {active_project.github_repo}")
        if active_project.folder:
            console.print(f"  Folder: {active_project.folder}")

        if plan.priorities:
            console.print("\n[bold]Today's Priorities[/bold]")
            for i, task in enumerate(plan.priorities, start=1):
                console.print(f"  {i}. {task.title}")
        if plan.suggested_prompt:
            console.print(f"\n[bold]Suggested Prompt[/bold]  {plan.suggested_prompt}")
        if plan.suggested_next_task:
            console.print(f"[bold]Suggested Next Task[/bold]  {plan.suggested_next_task.title}")

    console.print("\nGood day, Sayan.\n\nHow can I help?\n")


def _resolve_startup_project(planner: Planner) -> None:
    """Auto-detect the active project the way `cd` implies a shell context —
    workspace discovery first, registry second, never the other way around.

    1. Walk up from cwd looking for a real project marker (.git,
       pyproject.toml, package.json, go.mod, Cargo.toml, ...). If found and
       already registered, Planner activates it — no prompt, no command.
    2. If found but not registered, this is a real project Mads has never
       seen: print the detected name/workspace/repo and offer to register.
    3. If cwd isn't inside any recognizable project, fall back to the last
       active project and ask to resume it — otherwise no project is active.
    """
    project, unregistered_root = planner.resolve_startup_project(Path.cwd())

    if unregistered_root is not None:
        _offer_to_register(planner, unregistered_root)
        return

    if project is not None and planner.projects.get_active() is not None:
        # Already resolved to a registered project via cwd match.
        return

    if project is not None:
        console.print(f"\nGood morning. Last active project: [bold]{project.name}[/bold]")
        answer = console.input("Continue? [Y/n] ").strip().lower()
        if answer in {"", "y", "yes"}:
            planner.projects.set_active(project.slug)
        else:
            planner.projects.clear_active()


def _offer_to_register(planner: Planner, workspace_root: Path) -> None:
    name = planner.projects.suggest_project_name(workspace_root)
    github_repo = planner.projects.detect_github_repo(workspace_root)

    console.print("\nI detected a new project:")
    console.print(f"  Name: [bold]{name}[/bold]")
    console.print(f"  Workspace: {workspace_root}")
    if github_repo:
        console.print(f"  GitHub: {github_repo}")

    answer = console.input("Register it? [Y/n] ").strip().lower()
    if answer not in {"", "y", "yes"}:
        return

    planner.register_workspace(workspace_root)


async def _prompt_create_project(planner: Planner, name: str) -> None:
    """Manual fallback for registering a project from outside its folder.

    Workspace discovery at startup (see _resolve_startup_project) is the
    primary path — this exists for cases like "register ~/code/other-repo"
    while sitting somewhere else. GitHub repo is still inferred from the
    folder's git remote, never asked for directly.
    """
    folder_input = console.input("Local folder (optional, defaults to current directory): ").strip()
    folder = Path(folder_input).expanduser().resolve() if folder_input else Path.cwd()
    drive_folder = console.input("Google Drive folder (optional): ").strip() or None

    try:
        project = planner.projects.create(
            name,
            github_repo=planner.projects.detect_github_repo(folder),
            folder=str(folder),
            drive_folder=drive_folder,
        )
    except Exception as exc:  # noqa: BLE001 — surface any registration failure to the user
        console.print(f"[red]{exc}[/red]")
        return

    console.print(f"[green]✓[/green] Created project [bold]{project.name}[/bold]")
    if project.github_repo:
        console.print(f"  GitHub: {project.github_repo} (detected from git remote)")


def _print_dashboard(planner: Planner) -> None:
    view = planner.project_dashboard()
    if view is None:
        console.print("[dim]No active project.[/dim]")
        return

    console.print(f"\n[bold]{view.project.name}[/bold]")
    if view.project.github_repo:
        console.print(f"  Repository: {view.project.github_repo}")
    if view.project.folder:
        console.print(f"  Workspace: {view.project.folder}")
    if view.branch:
        console.print(f"  Branch: {view.branch}")
    console.print(f"  Open Tasks: {view.open_tasks}")
    console.print(f"  Completed Tasks: {view.completed_tasks}")
    console.print(f"  Progress: {view.progress_pct}%")
    if view.recent_commits:
        console.print("  Recent Commits:")
        for commit in view.recent_commits:
            console.print(f"    {commit}")
    if view.recent_documents:
        console.print("  Recent Documents:")
        for doc in view.recent_documents:
            console.print(f"    {doc}")
    if view.recommended_next_task:
        console.print(f"  Recommended Next Task: {view.recommended_next_task.title}")
    console.print()


async def _run_chatgpt_import(settings: Settings, export_path_str: str) -> None:
    """CLI-only by design (see adaptive.schemas) — a slow, real-cost bulk
    pipeline stays under explicit manual control rather than something
    Gemini can trigger mid-conversation. Nothing here writes to the
    Adaptive Profile directly; everything lands in the pending queue for
    review via list_pending_candidates/approve_candidate/reject_candidate.
    """
    export_dir = Path(export_path_str).expanduser().resolve()
    if not export_dir.is_dir():
        console.print(f"[red]Not a directory: {export_dir}[/red]")
        return

    console.print(f"\n[dim]Importing ChatGPT export from {export_dir}…[/dim]")
    console.print("[dim]This reads exported conversations and makes batched Gemini calls to classify/extract/score candidates — can take a few minutes for a large export.[/dim]\n")

    with console.status("[dim]running import pipeline…[/dim]", spinner="dots"):
        stats = await run_import(settings, export_dir)

    console.print(f"[green]✓[/green] Import complete")
    console.print(f"  Conversations in export: {stats.total_in_export}")
    console.print(f"  Already processed (skipped): {stats.already_processed}")
    console.print(f"  Gated out (too short/trivial): {stats.gated_out}")
    console.print(f"  Classified: {stats.classified}")
    console.print(f"  Worth learning: {stats.worth_learning}")
    console.print(f"  Candidates extracted: {stats.candidates_extracted}")
    console.print(f"  Candidates after dedup/scoring: {stats.candidates_scored}")
    console.print(f"  New items in approval queue: {len(stats.enqueued)}")

    if stats.enqueued:
        console.print("\n[bold]Review with the 'adaptive' tools in chat[/bold] — ask Mads to \"show pending candidates\" \nto approve/reject, nothing is learned automatically.\n")


def _print_plan(planner: Planner) -> None:
    plan = planner.daily_plan()
    if plan.project_name is None:
        console.print("[dim]No active project.[/dim]")
        return

    console.print(f"\n[bold]{plan.summary}[/bold]")
    for i, task in enumerate(plan.priorities, start=1):
        console.print(f"  {i}. {task.title}")
    if plan.suggested_prompt:
        console.print(f"\nSuggested Prompt: {plan.suggested_prompt}")
    if plan.suggested_next_task:
        console.print(f"Suggested Next Task: {plan.suggested_next_task.title}")
    console.print()


async def _run_repl() -> None:
    base_settings = get_settings()
    _configure_logging(base_settings.log_level)

    planner = Planner()
    adaptive_profile = AdaptiveProfile()
    _resolve_startup_project(planner)
    session = await _build_session(base_settings, planner, adaptive_profile, Path.cwd())

    try:
        _print_banner(session, planner)

        while True:
            try:
                user_input = console.input("[bold]>[/bold] ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print()
                break

            if not user_input:
                continue

            command = user_input.lower()
            if command in {"exit", "quit"}:
                break
            if command == "clear":
                console.clear()
                continue
            if command == "help":
                console.print(_HELP_TEXT)
                continue
            if command == "dashboard":
                _print_dashboard(planner)
                continue
            if command == "plan":
                _print_plan(planner)
                continue

            if command.startswith("create project "):
                name = user_input.split(" ", 2)[2].strip()
                if not name:
                    console.print("[red]Usage: create project <name>[/red]")
                    continue
                await _prompt_create_project(planner, name)
                continue

            if command.startswith("use project ") or command.startswith("switch project "):
                name = user_input.split(" ", 2)[2].strip()
                try:
                    planner.switch_project(name)
                except Exception as exc:  # noqa: BLE001 — surface lookup failure to the user
                    console.print(f"[red]{exc}[/red]")
                    continue

                await session.mcp_manager.aclose()
                session = await _build_session(base_settings, planner, adaptive_profile, Path.cwd())
                active = planner.projects.get_active()
                console.print(f"[green]✓[/green] Active Project: [bold]{active.name}[/bold]\n")
                continue

            if command.startswith("import chatgpt "):
                export_path_str = user_input.split(" ", 2)[2].strip()
                if not export_path_str:
                    console.print("[red]Usage: import chatgpt <path-to-export-folder>[/red]")
                    continue
                await _run_chatgpt_import(session.settings, export_path_str)
                # Approved facts only reach the system prompt on the next
                # session build (restart, or a project switch which already
                # rebuilds it) — Gemini's chat session holds a fixed
                # system_instruction set at construction time, so approvals
                # made later this session take effect next time, not live.
                continue

            if command.startswith("research "):
                topic = user_input[len("research "):].strip()
                message = build_research_prompt(topic)
                status_text = f"[dim]researching '{topic}'…[/dim]"
            else:
                message = user_input
                status_text = "[dim]thinking…[/dim]"

            with console.status(status_text, spinner="dots"):
                reply = await session.agent.send(message)
            planner.record_action(user_input[:120])
            console.print(reply)
            console.print()
    finally:
        await session.mcp_manager.aclose()

    console.print("[dim]Goodbye, Sayan.[/dim]")


def run() -> None:
    asyncio.run(_run_repl())


if __name__ == "__main__":
    run()
