"""Skills management commands."""
import typer
from typing import Optional
import os
from rich.console import Console
from rich.table import Table

from ..ui.theme import ThemeName, THEMES
from ..ui.layout import ui_state
from ..tools.skill_loader import SkillLoader


skills_app = typer.Typer(help="Skills 管理")


@skills_app.command("list")
def skills_list(
    profile: str = typer.Option(os.environ.get("MOCO_PROFILE", "entity"), "--profile", "-p", help="プロファイル"),
):
    """インストール済み Skills 一覧"""
    console = Console()
    theme = THEMES.get(ui_state.theme, THEMES[ThemeName.DEFAULT])
    loader = SkillLoader(profile=profile)
    skills = loader.list_installed_skills()

    if not skills:
        console.print(f"[dim]No skills installed in profile '{profile}'[/dim]")
        console.print("[dim]Try: moco skills sync anthropics[/dim]")
        return

    table = Table(title=f"Skills ({profile})", border_style=theme.tools)
    table.add_column("Name", style=theme.tools)
    table.add_column("Description", style=theme.result)
    table.add_column("Version", style=theme.status)
    table.add_column("Source", style="dim")

    for s in skills:
        table.add_row(
            s["name"],
            s["description"][:50] + ("..." if len(s["description"]) > 50 else ""),
            s["version"],
            s["source"][:30] + ("..." if len(s["source"]) > 30 else ""),
        )

    console.print(table)


@skills_app.command("install")
def skills_install(
    repo: str = typer.Argument(..., help="GitHub リポジトリ (例: anthropics/skills)"),
    skill_name: Optional[str] = typer.Argument(None, help="スキル名（省略時は全スキル）"),
    profile: str = typer.Option(os.environ.get("MOCO_PROFILE", "entity"), "--profile", "-p", help="プロファイル"),
    branch: str = typer.Option("main", "--branch", "-b", help="ブランチ"),
):
    """GitHub から Skills をインストール"""
    console = Console()
    loader = SkillLoader(profile=profile)

    if skill_name:
        # 単一スキルをインストール
        console.print(f"[dim]Installing skill '{skill_name}' from {repo}...[/dim]")
        success, message = loader.install_skill_from_github(repo, skill_name, branch)
        if success:
            console.print(f"[green]✅ {message}[/green]")
        else:
            console.print(f"[red]❌ {message}[/red]")
            raise typer.Exit(code=1)
    else:
        # 全スキルをインストール
        console.print(f"[dim]Installing all skills from {repo}...[/dim]")
        count, names = loader.install_skills_from_repo(repo, branch)
        if count > 0:
            console.print(f"[green]✅ Installed {count} skills:[/green]")
            for name in sorted(names):
                console.print(f"  - {name}")
        else:
            console.print("[yellow]No skills found in repository[/yellow]")


@skills_app.command("sync")
def skills_sync(
    registry: str = typer.Argument("anthropics", help="レジストリ名 (anthropics/community/claude-code/collection)"),
    profile: str = typer.Option(os.environ.get("MOCO_PROFILE", "entity"), "--profile", "-p", help="プロファイル"),
):
    """レジストリから Skills を同期"""
    console = Console()
    loader = SkillLoader(profile=profile)

    console.print(f"[dim]Syncing skills from '{registry}' registry...[/dim]")
    count, names = loader.sync_from_registry(registry)

    if count > 0:
        console.print(f"[green]✅ Synced {count} skills:[/green]")
        for name in sorted(names)[:20]:  # 最初の20件だけ表示
            console.print(f"  - {name}")
        if len(names) > 20:
            console.print(f"  ... and {len(names) - 20} more")
    else:
        console.print("[yellow]No skills found or sync failed[/yellow]")


@skills_app.command("uninstall")
def skills_uninstall(
    skill_name: str = typer.Argument(..., help="スキル名"),
    profile: str = typer.Option(os.environ.get("MOCO_PROFILE", "entity"), "--profile", "-p", help="プロファイル"),
):
    """Skill をアンインストール"""
    console = Console()
    loader = SkillLoader(profile=profile)

    success, message = loader.uninstall_skill(skill_name)
    if success:
        console.print(f"[green]✅ {message}[/green]")
    else:
        console.print(f"[red]❌ {message}[/red]")
        raise typer.Exit(code=1)


@skills_app.command("search")
def skills_search(
    query: str = typer.Argument(..., help="検索クエリ"),
    profile: str = typer.Option(os.environ.get("MOCO_PROFILE", "entity"), "--profile", "-p", help="プロファイル"),
):
    """インストール済み Skills を検索"""
    console = Console()
    theme = THEMES.get(ui_state.theme, THEMES[ThemeName.DEFAULT])
    loader = SkillLoader(profile=profile)
    results = loader.search_skills(query)

    if not results:
        console.print(f"[dim]No skills matching '{query}'[/dim]")
        return

    table = Table(title=f"Search: {query}", border_style=theme.tools)
    table.add_column("Name", style=theme.tools)
    table.add_column("Description", style=theme.result)
    table.add_column("Triggers", style="dim")

    for s in results:
        table.add_row(
            s["name"],
            s["description"][:50],
            ", ".join(s["triggers"][:3]),
        )

    console.print(table)


@skills_app.command("info")
def skills_info():
    """Skills レジストリ情報"""
    console = Console()

    table = Table(title="Available Registries", border_style="cyan")
    table.add_column("Name", style="cyan")
    table.add_column("Repository", style="white")
    table.add_column("Description", style="dim")

    registries = [
        ("anthropics", "anthropics/skills", "公式 Claude Skills"),
        ("community", "alirezarezvani/claude-skills", "コミュニティ Skills"),
        ("remotion", "remotion-dev/skills", "Remotion 動画生成 Skills"),
        ("claude-code", "daymade/claude-code-skills", "Claude Code 特化"),
        ("collection", "abubakarsiddik31/claude-skills-collection", "キュレーション集"),
    ]

    for name, repo, desc in registries:
        table.add_row(name, repo, desc)

    console.print(table)
    console.print()
    console.print("[dim]Usage: moco skills sync <registry-name>[/dim]")
    console.print("[dim]Example: moco skills sync anthropics[/dim]")
