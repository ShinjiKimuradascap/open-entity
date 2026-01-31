"""Profile management commands."""
import typer
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table

from ..ui.theme import ThemeName, THEMES
from ..ui.layout import ui_state


def list_profiles_cmd():
    """利用可能なプロファイル一覧"""
    profiles_dir = Path.cwd() / "moco" / "profiles"
    if not profiles_dir.exists():
        profiles_dir = Path("moco/profiles")

    typer.echo("Available profiles:")
    if profiles_dir.exists():
        found = False
        for p in sorted(profiles_dir.iterdir()):
            if p.is_dir() and (p / "profile.yaml").exists():
                typer.echo(f"  - {p.name}")
                found = True
        if not found:
            typer.echo("  (none found)")
    else:
        typer.echo(f"  Profile directory not found: {profiles_dir}")


def complete_profile(incomplete: str):
    """プロファイル名の自動補完"""
    profiles_dir = Path.cwd() / "moco" / "profiles"
    if not profiles_dir.exists():
        return []
    
    profiles = []
    for p in profiles_dir.iterdir():
        if p.is_dir() and (p / "profile.yaml").exists():
            if p.name.startswith(incomplete):
                profiles.append(p.name)
    return profiles


def version_cmd(
    detailed: bool = typer.Option(False, "--detailed", "-d", help="依存関係のバージョンも表示"),
):
    """バージョン表示"""
    from importlib.metadata import version as get_version, PackageNotFoundError
    
    console = Console()
    
    try:
        v = get_version("open-entity")
    except PackageNotFoundError:
        v = "0.2.0"
    
    if not detailed:
        typer.echo(f"Open Entity v{v}")
        return
    
    table = Table(title=f"Open Entity v{v}", border_style="cyan")
    table.add_column("Package", style="cyan")
    table.add_column("Version")
    
    core_deps = [
        "typer", "rich", "pydantic", "pyyaml", "fastapi", "uvicorn",
        "sqlmodel", "alembic", "httpx", "aiohttp", "openai",
        "google-generativeai", "google-genai", "tiktoken", "numpy",
        "faiss-cpu", "python-dotenv", "PyGithub", "networkx", "prompt_toolkit",
    ]
    
    for dep in core_deps:
        try:
            dep_version = get_version(dep)
            table.add_row(dep, dep_version)
        except PackageNotFoundError:
            table.add_row(dep, "[dim]not installed[/dim]")
    
    console.print(table)


def register_commands(app: typer.Typer):
    """コマンドをTyperアプリに登録"""
    app.command("list-profiles")(list_profiles_cmd)
    app.command("version")(version_cmd)
