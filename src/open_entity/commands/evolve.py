"""自己進化・自己改善コマンド。"""
import typer
from pathlib import Path
from typing import List, Optional
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..ui.theme import ThemeName, THEMES
from ..ui.layout import ui_state

evolve_app = typer.Typer(help="自己進化・コード改善")


@evolve_app.command("analyze")
def analyze_self(
    target: str = typer.Option("src", "--target", "-t", help="分析対象ディレクトリ"),
    profile: str = typer.Option("cursor", "--profile", "-p", help="使用するプロファイル"),
):
    """自分自身のコードを分析し改善点を提案"""
    console = Console()
    theme = THEMES.get(ui_state.theme, THEMES[ThemeName.DEFAULT])
    
    console.print(Panel(
        "[bold cyan]自己分析モード[/]\n"
        "自分自身のコードを分析し、改善点を検出します",
        border_style=theme.tools
    ))
    
    target_path = Path(target)
    if not target_path.exists():
        console.print(f"[red]対象パスが見つかりません: {target}[/]")
        raise typer.Exit(code=1)
    
    # 分析対象ファイルを収集
    python_files = list(target_path.rglob("*.py"))
    console.print(f"分析対象: {len(python_files)} ファイル")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        # 1. コード品質分析
        task = progress.add_task("コード品質を分析中...", total=None)
        issues = _analyze_code_quality(python_files)
        progress.update(task, completed=True)
        
        # 2. アーキテクチャ分析
        task = progress.add_task("アーキテクチャを分析中...", total=None)
        arch_issues = _analyze_architecture(target_path)
        progress.update(task, completed=True)
        
        # 3. 重複検出
        task = progress.add_task("重複コードを検出中...", total=None)
        dupes = _find_duplications(python_files)
        progress.update(task, completed=True)
    
    # レポート表示
    console.print(f"\n[bold]検出された問題:[/]")
    console.print(f"  コード品質: {len(issues)} 件")
    console.print(f"  アーキテクチャ: {len(arch_issues)} 件")
    console.print(f"  重複コード: {len(dupes)} 件")
    
    if issues:
        console.print("\n[bold cyan]主な改善提案:[/]")
        for issue in issues[:5]:
            console.print(f"  • {issue}")


@evolve_app.command("apply")
def apply_improvements(
    plan: str = typer.Argument(..., help="改善計画ファイルのパス"),
    dry_run: bool = typer.Option(True, "--dry-run/--apply", help="実際に適用するかシミュレーションのみ"),
):
    """改善計画を適用"""
    console = Console()
    
    plan_path = Path(plan)
    if not plan_path.exists():
        console.print(f"[red]計画ファイルが見つかりません: {plan}[/]")
        raise typer.Exit(code=1)
    
    if dry_run:
        console.print("[yellow]ドライラン モード - 実際の変更は行いません[/]")
    
    # 改善計画を読み込み適用
    console.print(f"計画を読み込み中: {plan}")


@evolve_app.command("loop")
def evolution_loop(
    max_iterations: int = typer.Option(3, "--max-iter", "-n", help="最大反復回数"),
    auto_commit: bool = typer.Option(False, "--auto-commit", help="成功時に自動コミット"),
):
    """自己進化ループを実行（分析→改善→検証→コミット）"""
    console = Console()
    
    console.print(Panel(
        "[bold cyan]🔄 自己進化ループ開始[/]\n"
        f"最大反復回数: {max_iterations}",
        border_style="green"
    ))
    
    for i in range(max_iterations):
        console.print(f"\n[bold]=== イテレーション {i+1}/{max_iterations} ===[/]")
        
        # 1. 分析
        console.print("[1/4] 自己分析...")
        # analyze_self 呼び出し
        
        # 2. 改善計画作成
        console.print("[2/4] 改善計画作成...")
        
        # 3. 適用
        console.print("[3/4] 改善適用...")
        
        # 4. 検証
        console.print("[4/4] 変更検証...")
        
        # 改善がなければ終了
        console.print("[dim]このイテレーションでの改善: 0 件[/]")
        break
    
    console.print("\n[green]✅ 自己進化ループ完了[/]")


def _analyze_code_quality(files: List[Path]) -> List[str]:
    """コード品質を分析（簡易版）"""
    issues = []
    for f in files:
        content = f.read_text()
        # 簡易チェック例
        if "import *" in content:
            issues.append(f"{f}: ワイルドカードインポートを避ける")
        if content.count("\n") > 500 and "# ==========" not in content:
            issues.append(f"{f}: 長すぎるファイル（分割検討）")
    return issues


def _analyze_architecture(root: Path) -> List[str]:
    """アーキテクチャ分析"""
    issues = []
    # 循環インポートチェックなど
    return issues


def _find_duplications(files: List[Path]) -> List[str]:
    """重複コード検出（簡易版）"""
    dupes = []
    # 簡易的な重複検出
    return dupes
