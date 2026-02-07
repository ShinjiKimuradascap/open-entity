import os
import secrets
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from ..utils.env_manager import EnvManager

console = Console()

class SetupWizard:
    def __init__(self):
        self.env = EnvManager()

    def run(self):
        console.clear()
        console.print(Panel.fit(
            "[bold cyan]Moco CLI - Setup Wizard[/bold cyan]\n"
            "[dim]Moco の構成をインタラクティブに設定します。[/dim]",
            border_style="cyan"
        ))

        # Step 1: Working Directory
        console.print("\n[bold green]Step 1: 作業ディレクトリの設定[/bold green]")
        console.print("Moco は、セーフティ規約に基づき、指定されたディレクトリ外の操作を制限します。")
        
        default_dir = os.environ.get("MOCO_WORKING_DIRECTORY") or os.getcwd()
        console.print(f"現在の推奨: [yellow]{default_dir}[/yellow]")
        
        while True:
            work_dir = Prompt.ask("作業ディレクトリのパスを入力してください", default=default_dir)
            work_dir_path = Path(work_dir).expanduser().resolve()
            
            if not work_dir_path.exists():
                if Confirm.ask(f"ディレクトリ {work_dir_path} は存在しません。作成しますか？"):
                    work_dir_path.mkdir(parents=True, exist_ok=True)
                else:
                    continue

            console.print(f"設定予定: [bold]{work_dir_path}[/bold]")
            if Confirm.ask("規約遵守：Mocoがこのディレクトリ内のみを操作することに同意しますか？"):
                self.env.update("MOCO_WORKING_DIRECTORY", str(work_dir_path))
                break

        # Step 2: Provider Selection
        console.print("\n[bold green]Step 2: LLM プロバイダの選択[/bold green]")
        provider = Prompt.ask(
            "デフォルトの LLM プロバイダを選択してください",
            choices=["openrouter", "openai", "gemini", "zai", "moonshot", "ollama", "anthropic"],
            default=os.environ.get("LLM_PROVIDER", "openrouter")
        )
        self.env.update("LLM_PROVIDER", provider)

        # Step 3: API Token (auto-generate)
        console.print("\n[bold green]Step 3: API トークンの生成[/bold green]")
        existing_token = os.environ.get("MOCO_API_TOKEN")
        if existing_token:
            console.print(f"既存のトークンが設定済みです: [dim]{existing_token[:8]}...[/dim]")
            if Confirm.ask("新しいトークンを再生成しますか？", default=False):
                token = secrets.token_urlsafe(32)
                self.env.update("MOCO_API_TOKEN", token)
                console.print(f"新しいトークン: [bold yellow]{token}[/bold yellow]")
            else:
                console.print("既存のトークンをそのまま使用します。")
        else:
            token = secrets.token_urlsafe(32)
            self.env.update("MOCO_API_TOKEN", token)
            console.print(f"APIトークンを自動生成しました: [bold yellow]{token}[/bold yellow]")
            console.print("[dim]WhatsApp等の外部連携で /api/chat を呼ぶ際に Bearer トークンとして使用されます。[/dim]")

        console.print()
        console.print(Panel.fit(
            "[bold green]✨ セットアップが完了しました！[/bold green]\n"
            "設定は [dim].env[/dim] ファイルに保存されました。",
            border_style="green"
        ))
        
        if Confirm.ask("今すぐ Moco を開始しますか？", default=True):
            return True
        return False
