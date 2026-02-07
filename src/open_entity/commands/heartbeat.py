"""Heartbeat management commands."""
import typer
import asyncio
import os
from typing import Optional
from rich.console import Console
from rich.panel import Panel

from .utils import init_environment

heartbeat_app = typer.Typer(help="ハートビート管理")

_DEFAULT_TEMPLATE = """# Heartbeat Checklist

以下の項目を定期的にチェックしてください。
全て問題なければ `HEARTBEAT_OK` と返答してください。

## チェック項目

- [ ] 重要なメール・通知の確認
- [ ] カレンダーの直近の予定
- [ ] 実行中のタスクの進捗

## 通知条件

- 緊急度の高い未読メールがある場合
- 30分以内に予定がある場合
- タスクが失敗している場合
"""


@heartbeat_app.command("status")
def heartbeat_status(
    profile: str = typer.Option(
        os.environ.get("MOCO_PROFILE", "entity"), "--profile", "-p",
        help="プロファイル"
    ),
):
    """ハートビート設定と状態を表示"""
    init_environment()
    console = Console()

    from ..tools.discovery import load_profile_config
    from ..core.heartbeat import HeartbeatConfig, HeartbeatRunner

    profile_config = load_profile_config(profile)
    config = HeartbeatConfig(profile_config)

    runner = HeartbeatRunner(
        config=config,
        orchestrator_factory=lambda: None,
        profile=profile,
    )
    status = runner.get_status()

    console.print(Panel(
        f"[bold]Enabled:[/] {config.enabled}\n"
        f"[bold]Interval:[/] {config.interval_seconds}s ({config.interval_seconds // 60}m)\n"
        f"[bold]Active Hours:[/] {status['active_hours'] or 'Always'}\n"
        f"[bold]Timezone:[/] {config.timezone}\n"
        f"[bold]ACK Token:[/] {config.ack_token}\n"
        f"[bold]HEARTBEAT.md:[/] {status['heartbeat_md']}\n"
        f"[bold]File Exists:[/] {status['heartbeat_md_exists']}\n"
        f"[bold]Beat Count:[/] {status['beat_count']}",
        title="Heartbeat Status",
        border_style="cyan",
    ))


@heartbeat_app.command("trigger")
def heartbeat_trigger(
    profile: str = typer.Option(
        os.environ.get("MOCO_PROFILE", "entity"), "--profile", "-p",
        help="プロファイル"
    ),
    provider: Optional[str] = typer.Option(
        None, "--provider", "-P",
        help="LLMプロバイダ (gemini/openai/openrouter/zai/moonshot/ollama)"
    ),
    model: Optional[str] = typer.Option(
        None, "--model", "-m",
        help="使用するモデル名"
    ),
):
    """ハートビートを手動で1回実行"""
    init_environment()
    console = Console()

    from ..tools.discovery import load_profile_config
    from ..core.heartbeat import HeartbeatConfig, HeartbeatRunner
    from ..core.orchestrator import Orchestrator
    from ..core.llm_provider import get_available_provider

    if provider is None:
        provider = get_available_provider()

    profile_config = load_profile_config(profile)
    config = HeartbeatConfig(profile_config)
    # trigger では enabled チェックをスキップ
    config.enabled = True

    def make_orchestrator():
        return Orchestrator(profile=profile, provider=provider, model=model, stream=False)

    runner = HeartbeatRunner(
        config=config,
        orchestrator_factory=make_orchestrator,
        profile=profile,
    )

    console.print("[dim]Executing heartbeat...[/dim]")

    try:
        result = asyncio.run(runner.trigger_once())
    except KeyboardInterrupt:
        console.print("\n[dim]Cancelled.[/dim]")
        raise typer.Exit()

    # ACK 判定
    is_ack = runner._is_ack(result)
    border = "green" if is_ack else "yellow"
    title = "Heartbeat Result (OK)" if is_ack else "Heartbeat Result (Alert)"
    console.print(Panel(result, title=title, border_style=border))


@heartbeat_app.command("edit")
def heartbeat_edit(
    profile: str = typer.Option(
        os.environ.get("MOCO_PROFILE", "entity"), "--profile", "-p",
        help="プロファイル"
    ),
):
    """HEARTBEAT.md をエディタで開く"""
    init_environment()

    from ..tools.discovery import load_profile_config
    from ..core.heartbeat import HeartbeatConfig, HeartbeatRunner

    profile_config = load_profile_config(profile)
    config = HeartbeatConfig(profile_config)

    runner = HeartbeatRunner(
        config=config,
        orchestrator_factory=lambda: None,
        profile=profile,
    )
    md_path = runner._heartbeat_md

    # ファイルが存在しなければテンプレートを作成
    if not md_path.exists():
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(_DEFAULT_TEMPLATE, encoding="utf-8")
        typer.echo(f"Created default HEARTBEAT.md at {md_path}")

    editor = os.environ.get("EDITOR", "vi")
    os.system(f'{editor} "{md_path}"')
