"""Profile management commands."""
import typer
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table

from ..ui.theme import ThemeName, THEMES
from ..ui.layout import ui_state


@app.command("list-profiles")
def list_profiles_cmd():
    """利用可能なプロファイル一覧"""
    _list_profiles()


def _list_profiles():
    """利用可能なプロファイル一覧"""
    profiles_dir = Path.cwd() / "moco" / "profiles"
    if not profiles_dir.exists():
        # Fallback to absolute path from project root if possible, or current dir
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


@app.command("version")
def version(
    detailed: bool = typer.Option(False, "--detailed", "-d", help="依存関係のバージョンも表示"),
):
    """バージョン表示"""
    from importlib.metadata import version as get_version, PackageNotFoundError
    
    console = Console()
    
    try:
        v = get_version("moco")
    except PackageNotFoundError:
        v = "0.2.0"
    
    if not detailed:
        typer.echo(f"Moco v{v}")
        return
    
    # 詳細表示モード
    table = Table(title=f"Moco v{v}", border_style="cyan")
    table.add_column("Package", style="cyan")
    table.add_column("Version")
    
    # コア依存関係
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
