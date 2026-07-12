from __future__ import annotations

import asyncio
import logging

from rich.console import Console

from agent.agent import Agent
from agent.research_prompt import build_research_prompt
from config.settings import Settings, get_settings
from mcp_servers.manager import MCPManager, StdioToolProvider, ToolProvider
from mcp_servers.servers import context7 as context7_server
from mcp_servers.servers import fetch as fetch_server
from mcp_servers.servers import filesystem as filesystem_server
from mcp_servers.servers import github as github_server
from mcp_servers.servers import spotify as spotify_server
from mcp_servers.servers import youtube as youtube_server
from mcp_servers.servers.document_intelligence import DocumentIntelligenceProvider
from mcp_servers.servers.google_workspace import GoogleWorkspaceProvider
from mcp_servers.servers.system import SystemProvider
from memory.provider import MemoryProvider
from memory.recall import build_recall_summary

console = Console()

_HELP_TEXT = """\
Commands:
  exit, quit         Leave Mads
  clear              Clear the screen
  help               Show this message
  research <topic>   Deep-dive research using Context7, GitHub, Fetch, and \
YouTube together, synthesized into an executive report
"""


def _build_providers(settings: Settings) -> list[ToolProvider]:
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
    providers.append(DocumentIntelligenceProvider(settings))
    providers.append(MemoryProvider(settings))
    providers.append(SystemProvider(settings))
    return providers


_KNOWN_SERVER_NAMES = [
    "filesystem",
    "fetch",
    "context7",
    "github",
    "google_workspace",
    "youtube",
    "spotify",
    "document_intelligence",
    "memory",
    "system",
]


def _print_banner(mcp_manager: MCPManager) -> None:
    console.print("\n[bold cyan]Mads v1[/bold cyan]\n")
    console.print("Connected:")
    connected = set(mcp_manager.connected_servers)
    for name in _KNOWN_SERVER_NAMES:
        mark = "[green]✓[/green]" if name in connected else "[red]✗[/red]"
        console.print(f"{mark} {name.capitalize()}")
    console.print("\nGood day, Sayan.\n\nHow can I help?\n")


def _configure_logging(log_level: str) -> None:
    logging.basicConfig(level=log_level)
    if log_level != "DEBUG":
        for noisy in ("httpx", "google_genai", "mcp"):
            logging.getLogger(noisy).setLevel(logging.WARNING)


async def _run_repl() -> None:
    settings = get_settings()
    _configure_logging(settings.log_level)

    providers = _build_providers(settings)
    mcp_manager = MCPManager()
    await mcp_manager.connect(providers)

    try:
        memory_context = build_recall_summary()
        agent = Agent(settings=settings, mcp_manager=mcp_manager, memory_context=memory_context)
        _print_banner(mcp_manager)

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

            if command.startswith("research "):
                topic = user_input[len("research "):].strip()
                message = build_research_prompt(topic)
                status_text = f"[dim]researching '{topic}'…[/dim]"
            else:
                message = user_input
                status_text = "[dim]thinking…[/dim]"

            with console.status(status_text, spinner="dots"):
                reply = await agent.send(message)
            console.print(reply)
            console.print()
    finally:
        await mcp_manager.aclose()

    console.print("[dim]Goodbye, Sayan.[/dim]")


def run() -> None:
    asyncio.run(_run_repl())


if __name__ == "__main__":
    run()
