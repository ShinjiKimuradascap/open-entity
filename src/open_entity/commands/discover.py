"""
Local AI Agent Discovery Commands

ローカルネットワーク内のAIエージェントを発見・登録するコマンド。
"""

import asyncio
import logging
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from ..discovery import MDNSServiceDiscovery, discover_local_agents, register_local_agent

logger = logging.getLogger(__name__)
console = Console()

discover_app = typer.Typer(
    name="discover",
    help="🔍 ローカルネットワーク内のAIエージェントを発見",
    no_args_is_help=True
)


@discover_app.callback()
def discover_callback():
    """ローカルAIエージェント発見機能"""
    pass


@discover_app.command("scan")
def scan_agents(
    timeout: float = typer.Option(3.0, "--timeout", "-t", help="検索時間（秒）"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="詳細表示"),
):
    """
    ローカルネットワーク内のAIエージェントをスキャン
    
    同じWiFi/ネットワーク内のOpen Entity互換AIを自動発見します。
    インフラ不要でピアツーピア接続が可能です。
    """
    console.print("🔍 [bold cyan]ローカルAIエージェントを検索中...[/bold cyan]\n")
    
    try:
        agents = asyncio.run(discover_local_agents(timeout=timeout))
        
        if not agents:
            console.print(Panel(
                "❌ 発見されたエージェントはありません\n\n"
                "ヒント: 同じWiFi内に他のAIが起動しているか確認してください\n"
                "      'oe discover advertise' で自分を発見可能にできます",
                title="結果",
                border_style="yellow"
            ))
            return
        
        # テーブル表示
        table = Table(
            title=f"🤖 {len(agents)}個のAIエージェントを発見",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold magenta"
        )
        
        table.add_column("名前", style="cyan", no_wrap=True)
        table.add_column("ID", style="green")
        table.add_column("エンドポイント", style="blue")
        table.add_column("機能", style="yellow")
        
        for agent in agents:
            caps = ", ".join(agent.capabilities[:3])
            if len(agent.capabilities) > 3:
                caps += f" (+{len(agent.capabilities)-3})"
            
            table.add_row(
                agent.name.replace("._openentity._tcp.local.", ""),
                agent.agent_id[:20] + "..." if len(agent.agent_id) > 20 else agent.agent_id,
                agent.a2a_endpoint,
                caps or "-"
            )
        
        console.print(table)
        
        if verbose:
            console.print("\n[dim]詳細情報:[/dim]")
            for agent in agents:
                console.print(f"\n  [cyan]{agent.name}[/cyan]")
                console.print(f"    アドレス: {', '.join(agent.addresses)}")
                console.print(f"    プロパティ: {agent.properties}")
                
    except ImportError as e:
        console.print(Panel(
            f"⚠️  {e}\n\n"
            "解決方法: pip install zeroconf",
            title="依存関係エラー",
            border_style="red"
        ))
        raise typer.Exit(1)
    except Exception as e:
        console.print(Panel(
            f"❌ エラー: {e}",
            title="検索失敗",
            border_style="red"
        ))
        raise typer.Exit(1)


@discover_app.command("advertise")
def advertise_agent(
    agent_id: Optional[str] = typer.Option(None, "--id", help="エージェントID（デフォルト: ホスト名）"),
    port: int = typer.Option(8951, "--port", "-p", help="A2Aサービスポート"),
    capabilities: str = typer.Option("", "--caps", "-c", help="機能（カンマ区切り）"),
):
    """
    自分のAIエージェントをローカルネットワークに登録
    
    他のAIから発見されるように、mDNSでサービスを公開します。
    Ctrl+Cで停止できます。
    """
    import socket
    
    agent_id = agent_id or f"open-entity-{socket.gethostname()}"
    caps = [c.strip() for c in capabilities.split(",") if c.strip()]
    
    console.print(Panel(
        f"📡 エージェント登録を開始します\n\n"
        f"  ID: [cyan]{agent_id}[/cyan]\n"
        f"  ポート: [cyan]{port}[/cyan]\n"
        f"  機能: [cyan]{', '.join(caps) or 'None'}[/cyan]\n\n"
        f"同じネットワーク内の他のAIから発見可能になりました。\n"
        f"[dim]Ctrl+Cで停止[/dim]",
        title="ローカル登録",
        border_style="green"
    ))
    
    async def run():
        try:
            discovery = await register_local_agent(agent_id, port, caps)
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            await discovery.close()
            console.print("\n👋 登録を解除しました")
    
    try:
        asyncio.run(run())
    except ImportError as e:
        console.print(Panel(
            f"⚠️  {e}\n\n"
            "解決方法: pip install zeroconf",
            title="依存関係エラー",
            border_style="red"
        ))
        raise typer.Exit(1)


@discover_app.command("watch")
def watch_agents(
    timeout: float = typer.Option(3.0, "--timeout", "-t", help="初回検索時間"),
):
    """
    ローカルエージェントの変化をリアルタイム監視
    
    新規参加・離脱をリアルタイムに表示します。
    """
    console.print("👀 [bold cyan]ローカルAIエージェントを監視中...[/bold cyan]\n")
    
    def on_add(agent):
        console.print(f"[green]➕ 参加:[/green] {agent.name} @ {agent.a2a_endpoint}")
    
    def on_remove(agent):
        console.print(f"[red]➖ 離脱:[/red] {agent.name}")
    
    async def run():
        discovery = MDNSServiceDiscovery()
        try:
            await discovery.discover(timeout=timeout, on_add=on_add, on_remove=on_remove)
            console.print("[dim]監視を継続中... (Ctrl+Cで停止)[/dim]")
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            await discovery.close()
    
    try:
        asyncio.run(run())
    except ImportError as e:
        console.print(Panel(
            f"⚠️  {e}\n\n"
            "解決方法: pip install zeroconf",
            title="依存関係エラー",
            border_style="red"
        ))
        raise typer.Exit(1)


# cli_main.py統合用
def register_commands(app: typer.Typer):
    """メインCLIアプリにコマンドを登録"""
    app.add_typer(discover_app, name="discover")
