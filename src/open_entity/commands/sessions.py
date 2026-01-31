"""Session management commands."""
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from pathlib import Path

from ..ui.theme import ThemeName, THEMES
from ..ui.layout import ui_state
from ..storage.session_logger import SessionLogger


sessions_app = typer.Typer(help="セッション管理")


@sessions_app.command("list")
def sessions_list(
    limit: int = typer.Option(10, "--limit", "-n", help="表示件数"),
):
    """過去のセッション一覧"""
    console = Console()
    theme = THEMES.get(ui_state.theme, THEMES[ThemeName.DEFAULT])
    logger = SessionLogger()
    sessions = logger.list_sessions(limit=limit)

    if not sessions:
        console.print("[dim]セッションがありません[/dim]")
        return

    table = Table(title="Sessions", border_style=theme.tools)
    table.add_column("ID", style=theme.tools, width=13)
    table.add_column("Title", style=theme.result)
    table.add_column("Profile", style=theme.status)
    table.add_column("Created", style="dim")

    for s in sessions:
        table.add_row(
            s.get("session_id", "")[:8] + "...",
            s.get("title", "")[:40],
            s.get("profile", ""),
            s.get("created_at", "")[:19],
        )

    console.print(table)


@sessions_app.command("show")
def sessions_show(
    session_id: str = typer.Argument(..., help="セッションID（先頭数文字でもOK）"),
):
    """セッションの履歴表示"""
    theme = THEMES[ui_state.theme]
    console = Console()
    logger = SessionLogger()

    # 部分一致でセッションを検索
    sessions = logger.list_sessions(limit=100)
    found_id = None
    for s in sessions:
        if s.get("session_id", "").startswith(session_id):
            found_id = s.get("session_id")
            break

    if not found_id:
        console.print(f"[red]Session not found: {session_id}[/red]")
        raise typer.Exit(code=1)

    history = logger.get_agent_history(found_id, limit=50)

    console.print(Panel(f"Session: {found_id}", border_style=theme.tools))

    for msg in history:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user":
            console.print(f"[bold {theme.status}]User:[/] {content[:200]}...")
        else:
            console.print(f"[bold {theme.result}]Assistant:[/] {content[:200]}...")
        console.print()
