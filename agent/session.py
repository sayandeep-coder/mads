from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from adaptive.profile import AdaptiveProfile
from adaptive.provider import AdaptiveProvider
from agent.agent import Agent
from config.settings import Settings
from mcp_servers.manager import MCPManager, StdioToolProvider, ToolProvider
from mcp_servers.servers import context7 as context7_server
from mcp_servers.servers import fetch as fetch_server
from mcp_servers.servers import filesystem as filesystem_server
from mcp_servers.servers import github as github_server
from mcp_servers.servers import maps as maps_server
from mcp_servers.servers import search as search_server
from mcp_servers.servers import spotify as spotify_server
from mcp_servers.servers import youtube as youtube_server
from mcp_servers.servers.browser_control import BrowserControlProvider
from mcp_servers.servers.excel_control import ExcelControlProvider
from mcp_servers.servers.google_workspace import GoogleWorkspaceProvider
from mcp_servers.servers.image import ImageProvider
from mcp_servers.servers.system import SystemProvider
from memory.provider import MemoryProvider
from memory.recall import build_recall_summary
from planner.models import Project
from planner.planner import Planner
from planner.provider import PlannerProvider
from skills import build_registry

# Shared session-assembly logic — every entrypoint that wants a live Mads
# session (the CLI REPL, the web backend) builds one through here, so the
# provider list can't drift out of sync between the two.

KNOWN_SERVER_NAMES = [
    "filesystem",
    "fetch",
    "context7",
    "github",
    "google_workspace",
    "youtube",
    "spotify",
    "search",
    "maps",
    "memory",
    "system",
    "image",
    "planner",
    "adaptive",
    "browser_control",
    "excel_control",
]


def build_providers(
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
    from mcp_servers.servers.astrology import AstrologyProvider
    if AstrologyProvider.is_available(settings):
        providers.append(AstrologyProvider(settings))

    # Document generation/reading (PDF, PPTX, Excel, Docs) is no longer an
    # always-on provider — it's registered as skills instead (see
    # skills/build_registry), loaded into the live tool list on demand.
    providers.append(MemoryProvider(settings))
    providers.append(SystemProvider(settings))
    providers.append(ImageProvider(settings))
    providers.append(PlannerProvider(planner, settings, on_switch=on_project_switch))
    providers.append(AdaptiveProvider(adaptive_profile, settings))
    return providers


def settings_for_project(base_settings: Settings, project: Project | None) -> Settings:
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


async def build_session(
    base_settings: Settings, planner: Planner, adaptive_profile: AdaptiveProfile, cwd: Path
) -> Session:
    """(Re)build the live session around whatever Planner currently reports
    as the active project. Called once at startup and again on every
    project switch — a full MCP reconnect, since the filesystem server's
    allowed root and the system prompt both need to follow the switch.
    """
    session_context = planner.start_session(cwd)
    active_project = session_context.active_project.project if session_context.active_project else None
    settings = settings_for_project(base_settings, active_project)

    mcp_manager = MCPManager()

    async def on_project_switch(new_project: Project) -> None:
        # Tool-call side effect only sets state on disk; the actual live
        # reconnect happens once the caller (REPL loop, web session) sees
        # the switch and rebuilds.
        pass

    providers = build_providers(settings, planner, adaptive_profile, on_project_switch)
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
        skill_registry=build_registry(settings),
    )

    return Session(settings=settings, mcp_manager=mcp_manager, agent=agent)


async def build_browser_session(base_settings: Settings, bridge) -> Session:
    """Build a separate, lightweight session for the Chrome side panel: just
    browser_control (backed by `bridge`, the live extension websocket) plus
    memory, so the browser agent knows who Sayan is without also spinning up
    every stdio MCP subprocess (filesystem, github, ...) that a normal chat
    session needs but a "go to flipkart and search shoes" request never
    touches.

    google_workspace is the one exception, added when OAuth is configured:
    Google Sheets/Docs render their content on a <canvas>, not real DOM, so
    browser_control's click/type tools cannot edit them no matter how good
    the DOM heuristics get (see content.js's isCanvasGridApp) — the only
    correct way to edit a sheet the user is looking at is the real Sheets
    API (read_sheet/update_sheet), which is exactly what google_workspace
    already provides.

    Deliberately not routed through build_providers/build_session — those
    assume the CLI/web chat's full tool fleet and a Planner-tracked active
    project, neither of which the browser agent needs or should block on.
    """
    mcp_manager = MCPManager()
    providers: list[ToolProvider] = [
        BrowserControlProvider(bridge),
        MemoryProvider(base_settings),
    ]
    if GoogleWorkspaceProvider.is_available(base_settings):
        providers.append(GoogleWorkspaceProvider(base_settings))
    await mcp_manager.connect(providers)

    memory_context = build_recall_summary()
    agent = Agent(
        settings=base_settings,
        mcp_manager=mcp_manager,
        memory_context=memory_context,
        browser_mode=True,
        skill_registry=build_registry(base_settings),
    )

    return Session(settings=base_settings, mcp_manager=mcp_manager, agent=agent)


async def build_excel_session(base_settings: Settings, bridge) -> Session:
    """Build a separate, lightweight session for the Excel task pane: just
    excel_control (backed by `bridge`, the live Office add-in websocket)
    plus memory — same shape as build_browser_session, but for Excel
    instead of Chrome. Unlike the browser case, Excel's own JS API
    (Office.js's Excel.run()) has direct, structured access to the open
    workbook, so there's no DOM-heuristics layer here at all — read_range/
    write_range operate on real cell addresses, not guessed element ids.
    """
    mcp_manager = MCPManager()
    providers: list[ToolProvider] = [
        ExcelControlProvider(bridge),
        MemoryProvider(base_settings),
    ]
    await mcp_manager.connect(providers)

    memory_context = build_recall_summary()
    agent = Agent(
        settings=base_settings,
        mcp_manager=mcp_manager,
        memory_context=memory_context,
        excel_mode=True,
        skill_registry=build_registry(base_settings),
    )

    return Session(settings=base_settings, mcp_manager=mcp_manager, agent=agent)


def resolve_startup_project(planner: Planner, cwd: Path, *, auto_register: bool = False) -> None:
    """Auto-detect the active project the way `cd` implies a shell context —
    workspace discovery first, registry second, never the other way around.

    1. Walk up from cwd looking for a real project marker (.git,
       pyproject.toml, package.json, go.mod, Cargo.toml, ...). If found and
       already registered, Planner activates it.
    2. If found but not registered: interactive callers prompt (see
       cli/main.py); non-interactive callers (auto_register=True, e.g. the
       web backend, which has no console to prompt on) register it
       automatically — same auto-detected name/repo, no prompt possible.
    3. If cwd isn't inside any recognizable project, fall back to the last
       active project — resumed automatically for non-interactive callers,
       left to the caller to decide for interactive ones.
    """
    project, unregistered_root = planner.resolve_startup_project(cwd)

    if unregistered_root is not None:
        if auto_register:
            planner.register_workspace(unregistered_root)
        return

    if project is not None:
        planner.projects.set_active(project.slug)
