"""Task management commands."""
import typer
import os
from typing import Optional
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel

from ..storage.task_store import TaskStore
from ..core.task_runner import TaskRunner
from ..core.llm_provider import get_available_provider
from .utils import init_environment


tasks_app = typer.Typer(help="タスク管理")


def _truncate(text: str, max_len: int = 35) -> str:
    """説明文を短く切り詰める（最初の行のみ）"""
    first_line = text.split('\n')[0].strip()
    if len(first_line) > max_len:
        return first_line[:max_len] + "..."
    return first_line


def _format_duration(start_str: str, end_str: str = None) -> str:
    """経過時間をフォーマット"""
    if not start_str:
        return "-"
    try:
        start = datetime.fromisoformat(start_str)
        end = datetime.fromisoformat(end_str) if end_str else datetime.now()
        delta = end - start
        total_seconds = int(delta.total_seconds())

        if total_seconds < 60:
            return f"{total_seconds}s"
        elif total_seconds < 3600:
            mins = total_seconds // 60
            secs = total_seconds % 60
            return f"{mins}m {secs}s"
        else:
            hours = total_seconds // 3600
            mins = (total_seconds % 3600) // 60
            return f"{hours}h {mins}m"
    except Exception:
        return "-"


@tasks_app.command("run")
def tasks_run(
    task: str = typer.Argument(..., help="実行するタスク内容"),
    profile: str = typer.Option("default", "--profile", "-p", help="プロファイル"),
    provider: Optional[str] = typer.Option(None, "--provider", "-P", help="プロバイダ - 省略時は自動選択"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="使用するモデル名"),
    working_dir: Optional[str] = typer.Option(None, "--working-dir", "-w", help="作業ディレクトリ"),
    session: Optional[str] = typer.Option(None, "--session", "-s", help="継続するセッションID"),
):
    """タスクをバックグラウンドで実行"""
    init_environment()

    # プロバイダーの解決（指定なしの場合は優先順位で自動選択）
    if provider is None:
        provider = get_available_provider()
    
    # "zai/glm-4.7" のような形式をパース
    resolved_provider = provider
    resolved_model = model
    if "/" in provider and model is None:
        parts = provider.split("/", 1)
        resolved_provider = parts[0]
        resolved_model = parts[1]

    # 作業ディレクトリを絶対パスに解決
    resolved_working_dir = None
    if working_dir:
        resolved_working_dir = os.path.abspath(working_dir)

    store = TaskStore()
    task_id = store.add_task(task, profile, resolved_provider, resolved_working_dir)

    runner = TaskRunner(store)
    runner.run_task(task_id, profile, task, resolved_working_dir, resolved_provider, resolved_model)

    typer.echo(f"Task started: {task_id}")
    if session:
        typer.echo(f"Continuing session: {session}")


@tasks_app.command("list")
def tasks_list(
    limit: int = typer.Option(20, "--limit", "-l", help="表示件数"),
):
    """タスク一覧（経過時間付き）"""
    store = TaskStore()
    tasks = store.list_tasks(limit=limit)
    console = Console()

    # サマリー
    running = sum(1 for t in tasks if t["status"] == "running")
    completed = sum(1 for t in tasks if t["status"] == "completed")
    failed = sum(1 for t in tasks if t["status"] == "failed")

    console.print(f"\n🔄 Running: [yellow]{running}[/]  ✅ Done: [green]{completed}[/]  ❌ Failed: [red]{failed}[/]\n")

    table = Table(title="Task List")
    table.add_column("", width=2)  # アイコン
    table.add_column("ID", style="cyan", no_wrap=True, width=10)
    table.add_column("Description", max_width=35, no_wrap=True)
    table.add_column("Status", width=10)
    table.add_column("Duration", width=10, justify="right")
    table.add_column("Created", no_wrap=True, width=16)

    for t in tasks:
        status = t["status"]

        # アイコンと色
        icons = {
            "running": ("🔄", "yellow"),
            "completed": ("✅", "green"),
            "failed": ("❌", "red"),
            "pending": ("⏳", "dim"),
            "cancelled": ("🚫", "dim"),
        }
        icon, color = icons.get(status, ("❓", "white"))

        # 経過時間
        if status == "running":
            duration = _format_duration(t["started_at"])
        elif status in ("completed", "failed"):
            duration = _format_duration(t["started_at"], t["completed_at"])
        else:
            duration = "-"

        table.add_row(
            icon,
            t["task_id"][:10],
            _truncate(t["task_description"]),
            f"[{color}]{status}[/]",
            f"[{color}]{duration}[/]",
            t["created_at"][5:16].replace("T", " ")  # MM-DD HH:MM
        )

    console.print(table)


@tasks_app.command("status")
def tasks_status():
    """リアルタイムダッシュボード（経過時間・進捗表示付き）"""
    import time
    
    store = TaskStore()
    console = Console()

    # スピナーのフレーム
    spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    frame_idx = [0]  # ミュータブルなカウンター

    def render():
        tasks = store.list_tasks(limit=50)
        
        # 統計
        running = sum(1 for t in tasks if t["status"] == "running")
        completed = sum(1 for t in tasks if t["status"] == "completed")
        failed = sum(1 for t in tasks if t["status"] == "failed")
        pending = sum(1 for t in tasks if t["status"] == "pending")

        # スピナー更新
        spinner = spinner_frames[frame_idx[0] % len(spinner_frames)]
        frame_idx[0] += 1

        table = Table(title=f"{spinner} Task Dashboard (Ctrl+C to exit)")
        table.add_column("", width=2)
        table.add_column("ID", style="cyan", width=10)
        table.add_column("Description", max_width=30)
        table.add_column("Status", width=10)
        table.add_column("Duration", width=10, justify="right")
        table.add_column("Progress", width=20)

        for t in tasks[:15]:  # 最新15件のみ
            status = t["status"]
            icons = {
                "running": ("🔄", "yellow"),
                "completed": ("✅", "green"),
                "failed": ("❌", "red"),
                "pending": ("⏳", "dim"),
            }
            icon, color = icons.get(status, ("❓", "white"))

            duration = _format_duration(t.get("started_at"), t.get("completed_at") if status != "running" else None)
            
            # 進捗バー（ダミー - 実際の進捗はタスクが報告する必要がある）
            progress = "─" * 15
            if status == "running":
                progress = f"[yellow]{'━' * 8}╺{'─' * 6}[/]"
            elif status == "completed":
                progress = f"[green]{'━' * 15}[/]"
            elif status == "failed":
                progress = f"[red]{'━' * 5}╺{'─' * 9}[/]"

            table.add_row(
                icon,
                t["task_id"][:8],
                _truncate(t["task_description"], 28),
                f"[{color}]{status}[/]",
                duration,
                progress
            )

        summary = f"Running: {running} | Completed: {completed} | Failed: {failed} | Pending: {pending}"
        return Panel(table, title=summary, border_style="blue")

    try:
        with Live(render(), refresh_per_second=4, console=console) as live:
            while True:
                time.sleep(0.25)
                live.update(render())
    except KeyboardInterrupt:
        console.print("\n[dim]Dashboard closed.[/dim]")


@tasks_app.command("logs")
def tasks_logs(
    task_id: str = typer.Argument(..., help="タスクID"),
    follow: bool = typer.Option(False, "--follow", "-f", help="リアルタイム更新"),
):
    """タスクのログを表示"""
    import time
    
    store = TaskStore()
    console = Console()

    def show_logs():
        logs = store.get_task_logs(task_id)
        if not logs:
            return "[dim]No logs found.[/dim]"
        return "\n".join(logs)

    if not follow:
        console.print(show_logs())
        return

    # フォローモード
    last_len = 0
    try:
        while True:
            logs = store.get_task_logs(task_id)
            if len(logs) > last_len:
                new_logs = logs[last_len:]
                console.print("\n".join(new_logs))
                last_len = len(logs)
            time.sleep(1)
    except KeyboardInterrupt:
        console.print("\n[dim]Log stream closed.[/dim]")


@tasks_app.command("cancel")
def tasks_cancel(
    task_id: str = typer.Argument(..., help="タスクID"),
):
    """実行中のタスクをキャンセル"""
    store = TaskStore()
    success = store.cancel_task(task_id)
    if success:
        typer.echo(f"Task {task_id} cancelled.")
    else:
        typer.echo(f"Task {task_id} not found or already finished.", err=True)
        raise typer.Exit(code=1)


@tasks_app.command("_exec", hidden=True)
def tasks_exec(
    task_id: str = typer.Argument(..., help="タスクID"),
    profile: str = typer.Option(..., "--profile", "-p"),
    working_dir: Optional[str] = typer.Option(None, "--working-dir", "-w"),
):
    """内部用: タスクを実行（直接呼び出し用）"""
    init_environment()
    
    store = TaskStore()
    task_info = store.get_task(task_id)
    if not task_info:
        typer.echo(f"Task {task_id} not found.", err=True)
        raise typer.Exit(code=1)

    runner = TaskRunner(store)
    runner.execute_task(task_id, task_info, profile, working_dir)
