#!/usr/bin/env python3
"""Moco CLI"""

# ruff: noqa: E402
import warnings
# ========================================
# 警告の抑制 (インポート前に設定)
# ========================================
# Python 3.9 EOL や SSL 関連の不要な警告を非表示にする
warnings.filterwarnings("ignore", category=FutureWarning)
try:
    # urllib3 の NotOpenSSLWarning はインポート時に発生するため、
    # 警告フィルターを先に設定しておく必要がある
    warnings.filterwarnings("ignore", message=".*urllib3 v2 only supports OpenSSL 1.1.1+.*")
    # Google GenAI の thought_signature 警告を抑制
    warnings.filterwarnings("ignore", message=".*non-text parts in the response.*")
    warnings.filterwarnings("ignore", message=".*thought_signature.*")
except Exception:
    pass

# ========================================
# 重要: .env の読み込みは最初に行う必要がある
# 他のモジュールがインポート時に環境変数を参照するため
# ========================================
import os
from pathlib import Path
from dotenv import load_dotenv, find_dotenv

def _early_load_dotenv():
    """モジュールインポート前に .env を読み込む"""
    env_path = find_dotenv(usecwd=True) or (Path(__file__).parent.parent.parent / ".env")
    if env_path:
        load_dotenv(env_path)

# 他のモジュールをインポートする前に環境変数を読み込む
_early_load_dotenv()

# ここから通常のインポート
import typer
import time
from typing import Optional, List
from .ui.theme import ThemeName, THEMES

def init_environment():
    """環境変数の初期化（後方互換性のために残す）"""
    # 既に _early_load_dotenv() で読み込み済みだが、
    # 明示的に呼ばれた場合は再読み込み
    env_path = find_dotenv(usecwd=True) or (Path(__file__).parent.parent.parent / ".env")
    if env_path:
        load_dotenv(env_path, override=True)

DEFAULT_PROFILE = os.environ.get("MOCO_PROFILE", "entity")

def resolve_provider(provider_str: str, model: Optional[str] = None) -> tuple:
    """プロバイダ文字列を解決してLLMProviderとモデル名を返す
    
    Args:
        provider_str: プロバイダ文字列 (例: "gemini", "zai/glm-4.7")
        model: モデル名（既に指定されている場合）
    
    Returns:
        tuple: (LLMProvider, model_name) - 無効なプロバイダの場合は typer.Exit を発生
    """
    from .core.runtime import LLMProvider
    
    # "zai/glm-4.7" のような形式をパース
    provider_name = provider_str
    resolved_model = model
    if "/" in provider_str and model is None:
        parts = provider_str.split("/", 1)
        provider_name = parts[0]
        resolved_model = parts[1]
    
    # プロバイダ名のバリデーションとマッピング
    VALID_PROVIDERS = {
        "openai": LLMProvider.OPENAI,
        "openrouter": LLMProvider.OPENROUTER,
        "zai": LLMProvider.ZAI,
        "gemini": LLMProvider.GEMINI,
        "moonshot": LLMProvider.MOONSHOT,
        "ollama": LLMProvider.OLLAMA,
    }
    
    if provider_name not in VALID_PROVIDERS:
        valid_list = ", ".join(sorted(VALID_PROVIDERS.keys()))
        typer.echo(f"Error: Unknown provider '{provider_name}'. Valid options: {valid_list}", err=True)
        raise typer.Exit(code=1)
    
    return VALID_PROVIDERS[provider_name], resolved_model


app = typer.Typer(
    name="Open Entity",
    help="Lightweight AI agent orchestration framework",
    add_completion=False,
)

# セッション管理用サブコマンド（commandsからインポート）
from .commands.sessions import sessions_app
app.add_typer(sessions_app, name="sessions")

# Skills 管理用サブコマンド（commandsからインポート）
from .commands.skills import skills_app
app.add_typer(skills_app, name="skills")

# タスク管理用サブコマンド（commandsからインポート）
from .commands.tasks import tasks_app
app.add_typer(tasks_app, name="tasks")

# 自己進化コマンド（commandsからインポート）
from .commands.evolve import evolve_app
app.add_typer(evolve_app, name="evolve")

# A2A通信コマンド（P2P）
from .commands.a2a import a2a_app
app.add_typer(a2a_app, name="a2a")

# Heartbeat管理用サブコマンド
from .commands.heartbeat import heartbeat_app
app.add_typer(heartbeat_app, name="heartbeat")

# profilesコマンドを登録（list-profiles, version等）
from .commands.profiles import register_commands
register_commands(app)


def get_available_profiles() -> List[str]:
    """利用可能なプロファイル一覧を取得"""
    profiles = []
    
    # 1. カレントディレクトリの profiles/
    cwd_profiles = Path.cwd() / "profiles"
    if cwd_profiles.exists():
        for p in cwd_profiles.iterdir():
            if p.is_dir() and (p / "profile.yaml").exists():
                profiles.append(p.name)
    
    # 2. パッケージ内蔵プロファイル
    pkg_profiles = Path(__file__).parent / "profiles"
    if pkg_profiles.exists():
        for p in pkg_profiles.iterdir():
            if p.is_dir() and (p / "profile.yaml").exists():
                if p.name not in profiles:
                    profiles.append(p.name)
    
    return sorted(profiles) if profiles else ["default"]


def complete_profile(incomplete: str) -> List[str]:
    """プロファイル名のタブ補完"""
    profiles = get_available_profiles()
    return [p for p in profiles if p.startswith(incomplete)]


def prompt_profile_selection() -> str:
    """対話的にプロファイルを選択"""
    from rich.prompt import Prompt
    from .ui.console import console
    profiles = get_available_profiles()
    
    if len(profiles) == 1:
        return profiles[0]
    
    console.print("\n[bold]Available profiles:[/]")
    for i, p in enumerate(profiles, 1):
        console.print(f"  [cyan]{i}[/]. {p}")
    
    choice = Prompt.ask(
        "\n[bold]Select profile[/]",
        choices=[str(i) for i in range(1, len(profiles) + 1)] + profiles,
        default="1"
    )
    
    # 数字で選択された場合
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(profiles):
            return profiles[idx]
    
    # 名前で選択された場合
    if choice in profiles:
        return choice
    
    return profiles[0]


@app.command()
def run(
    task: str = typer.Argument(..., help="実行するタスク"),
    profile: str = typer.Option(DEFAULT_PROFILE, "--profile", "-p", help="使用するプロファイル", autocompletion=complete_profile),
    provider: Optional[str] = typer.Option(None, "--provider", "-P", help="LLMプロバイダ (gemini/openai/openrouter/zai/moonshot/ollama) - 省略時は自動選択"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="使用するモデル名 (例: gpt-4o, gemini-2.5-pro, claude-sonnet-4)"),
    stream: bool = typer.Option(False, "--stream/--no-stream", help="ストリーミング出力（デフォルト: オフ）"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="詳細ログ"),
    rich_output: bool = typer.Option(True, "--rich/--plain", help="リッチ出力"),
    session: Optional[str] = typer.Option(None, "--session", "-s", help="セッション名（継続 or 新規）"),
    cont: bool = typer.Option(False, "--continue", "-c", help="直前のセッションを継続"),
    auto_retry: int = typer.Option(0, "--auto-retry", help="エラー時の自動リトライ回数"),
    retry_delay: int = typer.Option(3, "--retry-delay", help="リトライ間隔（秒）"),
    show_metrics: bool = typer.Option(False, "--show-metrics", "-M", help="メトリクス表示"),
    theme: ThemeName = typer.Option(ThemeName.DEFAULT, "--theme", help="UIカラーテーマ", case_sensitive=False),
    use_optimizer: bool = typer.Option(False, "--optimizer/--no-optimizer", help="Optimizerによるエージェント自動選択"),
    working_dir: Optional[str] = typer.Option(None, "--working-dir", "-w", help="作業ディレクトリ（subagentに自動伝達）"),
):
    """タスクを実行"""
    if session and cont:
        typer.echo("Error: --session と --continue は同時に指定できません。", err=True)
        raise typer.Exit(code=1)

    from .ui.layout import ui_state
    ui_state.theme = theme

    theme_config = THEMES[theme]

    init_environment()

    # 作業ディレクトリのバリデーションと設定
    if working_dir:
        path = Path(working_dir).resolve()
        if not path.is_dir():
            typer.echo(f"Error: Directory does not exist: {working_dir}", err=True)
            raise typer.Exit(code=1)
        os.environ['MOCO_WORKING_DIRECTORY'] = str(path)

    from .core.orchestrator import Orchestrator
    from .core.llm_provider import get_available_provider

    # プロバイダーの解決（指定なしの場合は優先順位で自動選択）
    if provider is None:
        provider = get_available_provider()

    provider_enum, model = resolve_provider(provider, model)

    if rich_output:
        from rich.panel import Panel
        from .ui.console import console

    o = Orchestrator(
        profile=profile,
        provider=provider_enum,
        model=model,
        stream=stream,
        verbose=verbose,
        use_optimizer=use_optimizer,
        working_directory=working_dir,
    )

    # セッション管理
    session_id = None
    if cont:
        # 直前のセッションを取得
        sessions = o.session_logger.list_sessions(limit=1)
        if sessions:
            session_id = sessions[0].get("session_id")
            if rich_output:
                console.print(f"[dim]Continuing session: {session_id[:8]}...[/dim]")
        else:
            typer.echo("Warning: 継続するセッションがありません。新規作成します。", err=True)
    elif session:
        # 名前付きセッションを検索または作成
        sessions = o.session_logger.list_sessions(limit=50)
        for s in sessions:
            if s.get("title", "").endswith(f"[{session}]"):
                session_id = s.get("session_id")
                if rich_output:
                    console.print(f"[dim]Resuming session: {session}[/dim]")
                break

    if not session_id:
        title = f"CLI: {task[:40]}" + (f" [{session}]" if session else "")
        session_id = o.create_session(title=title)

    if rich_output:
        header = f"[bold {theme_config.status}]Profile:[/] {profile}  [bold {theme_config.status}]Provider:[/] {provider}"
        if session:
            header += f"  [bold {theme_config.status}]Session:[/] {session}"
        console.print(Panel(header, title="🤖 Moco", border_style=theme_config.tools))
        console.print()

    # 実行（リトライ対応）
    start_time = time.time()
    result = None

    from .cancellation import create_cancel_event, request_cancel, clear_cancel_event, OperationCancelled
    create_cancel_event(session_id)

    try:
        for attempt in range(auto_retry + 1):
            try:
                result = o.run_sync(task, session_id)
                break
            except (KeyboardInterrupt, OperationCancelled):
                request_cancel(session_id)
                if rich_output:
                    console.print(f"\n[bold red]Cancelled[/bold red] (Session: {session_id[:8]}...)")
                else:
                    print(f"\nCancelled (Session: {session_id[:8]}...)")
                raise typer.Exit(code=0)
            except Exception as e:
                if attempt < auto_retry:
                    if rich_output:
                        console.print(f"[yellow]Error: {e}. Retrying in {retry_delay}s... ({attempt + 1}/{auto_retry})[/yellow]")
                    time.sleep(retry_delay)
                else:
                    if rich_output:
                        console.print(f"[red]Error: {e}[/red]")
                        _print_error_hints(console, e)
                    raise typer.Exit(code=1)
    finally:
        clear_cancel_event(session_id)

    elapsed = time.time() - start_time

    if rich_output and result:
        console.print()
        _print_result(console, result, theme_name=theme, verbose=verbose)

        if show_metrics:
            console.print()
            console.print(Panel(
                f"[bold]Elapsed:[/] {elapsed:.1f}s\n"
                f"[bold]Session:[/] {session_id[:8]}...",
                title="📊 Metrics",
                border_style=theme_config.status,
            ))
    elif result:
        print("\n--- Result ---")
        print(result)




def _print_error_hints(console, error: Exception):
    """エラー種別に応じたヒントを表示"""
    from rich.panel import Panel

    error_str = str(error).lower()
    hints = []

    if "rate limit" in error_str or "429" in error_str:
        hints.append("• レートリミットです。しばらく待ってから再実行してください。")
        hints.append("• --provider を変更してみてください。")
    elif "api key" in error_str or "authentication" in error_str:
        hints.append("• API キーを確認してください。")
        hints.append("• .env ファイルに正しいキーが設定されているか確認。")
    elif "context" in error_str or "token" in error_str:
        hints.append("• プロンプトが長すぎる可能性があります。")
        hints.append("• タスクを分割して実行してみてください。")
    else:
        hints.append("• --verbose オプションで詳細ログを確認してください。")
        hints.append("• --auto-retry でリトライを試してください。")

    console.print(Panel("\n".join(hints), title="💡 Hints", border_style="yellow"))


def _print_result(console, result: str, theme_name: ThemeName = ThemeName.DEFAULT, verbose: bool = False):
    """結果を整形して表示（シンプルテキスト出力）

    Args:
        console: Rich console
        result: 結果文字列
        verbose: True なら全エージェント出力を表示、False なら最後だけ
    """
    import re

    theme = THEMES[theme_name]

    # 最終サマリーを抽出
    final_summary = ""
    if "\n---\n## まとめ" in result:
        parts = result.split("\n---\n## まとめ")
        result = parts[0]
        final_summary = parts[1].strip() if len(parts) > 1 else ""
    elif "\n---\n✅" in result:
        parts = result.split("\n---\n✅")
        result = parts[0]
        final_summary = parts[1].strip() if len(parts) > 1 else ""

    # @agent: 応答 のパターンで分割
    sections = re.split(r'(@[\w-]+):\s*', result)

    if len(sections) > 1:
        if verbose:
            # 全エージェントの出力を表示
            i = 1
            while i < len(sections):
                agent = sections[i]
                content = sections[i + 1].strip() if i + 1 < len(sections) else ""
                if content:
                    # 長すぎる場合は切り詰め
                    lines = content.split('\n')
                    if len(lines) > 30:
                        content = '\n'.join(lines[:30]) + f"\n... ({len(lines) - 30} lines omitted)"
                    console.print(f"\n[bold {theme.thoughts}]{agent}[/]")
                    console.print(content)
                i += 2
        else:
            # 最後のエージェントの結果だけ表示
            last_agent = sections[-2] if len(sections) >= 2 else ""
            last_content = sections[-1].strip() if sections[-1] else ""

            # orchestrator の最終回答は省略しない、他は短縮
            if last_agent == "@orchestrator":
                display = last_content
            else:
                lines = last_content.split('\n')
                if len(lines) > 20:
                    display = '\n'.join(lines[:20]) + f"\n\n[dim]... ({len(lines) - 20} lines omitted, use -v for full output)[/dim]"
                else:
                    display = last_content

            console.print(f"\n[bold {theme.thoughts}]{last_agent}[/]")
            console.print(display)

    # 最終サマリーを表示
    if final_summary:
        console.print(f"\n[bold {theme.result}]✅ まとめ[/]")
        console.print(final_summary)
    elif len(sections) > 1:
        console.print(f"\n[bold {theme.result}]✅ 完了[/]")
    else:
        # 単一の応答
        console.print(result)


@app.command()
def chat(
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="使用するプロファイル", autocompletion=complete_profile),
    provider: Optional[str] = typer.Option(None, "--provider", "-P", help="LLMプロバイダ (gemini/openai/openrouter/zai/moonshot/ollama) - 省略時は自動選択"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="使用するモデル名"),
    stream: Optional[bool] = typer.Option(None, "--stream/--no-stream", help="ストリーミング出力（デフォルト: プロバイダ依存）"),
    subagent_stream: bool = typer.Option(False, "--subagent-stream/--no-subagent-stream", help="サブエージェント本文のストリーミング表示（デフォルト: オフ）"),
    tool_status: bool = typer.Option(True, "--tool-status/--no-tool-status", help="ツール/委譲の短いステータス行を表示（デフォルト: オン）"),
    todo_pane: bool = typer.Option(False, "--todo-pane/--no-todo-pane", help="Todo を右ペインに常時表示（デフォルト: オフ）"),
    async_input: bool = typer.Option(False, "--async-input/--no-async-input", help="処理中も入力を受け付けてキューイング（Gemini CLI風）"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="詳細ログ"),
    session: Optional[str] = typer.Option(None, "--session", "-s", help="セッション名（継続 or 新規）"),
    new_session: bool = typer.Option(False, "--new", help="新規セッションを強制開始"),
    theme: ThemeName = typer.Option(ThemeName.DEFAULT, "--theme", help="UIカラーテーマ", case_sensitive=False),
    use_optimizer: bool = typer.Option(False, "--optimizer/--no-optimizer", help="Optimizerによるエージェント自動選択"),
):
    """対話型チャット"""
    from .ui.layout import ui_state
    ui_state.theme = theme
    theme_config = THEMES[theme]

    init_environment()
    from .ui.console import console

    from .core.orchestrator import Orchestrator
    from .core.llm_provider import get_available_provider
    from .core.runtime import _safe_stream_print
    from .ui.status_line import StatusLine

    _status_line = StatusLine()
    _active_status: dict = {"text": "", "start_time": 0.0}

    stream_flags = {"show_subagent_stream": subagent_stream, "show_tool_status": tool_status}
    # Track whether we have printed any streamed text without a newline recently.
    # Used to avoid mixing tool logs into the middle of a line.
    stream_state = {"mid_line": False}

    # prompt_toolkit printing helpers (used in --async-input mode)
    pt_ansi_print = None

    # Async-input mode (Gemini CLI style):
    # - allow typing next prompts while the current one is processing
    # - enqueue prompts and execute sequentially in a worker thread
    if async_input and todo_pane:
        console.print("[yellow]--async-input is currently incompatible with --todo-pane. Disabling --async-input.[/yellow]")
        async_input = False
    if async_input:
        import sys
        if not sys.stdin.isatty():
            console.print("[yellow]--async-input requires an interactive TTY stdin. Disabling --async-input.[/yellow]")
            async_input = False

    # Optional: side pane for Todos (Rich Live layout)
    pane_state = {
        "enabled": bool(todo_pane),
        "live": None,
        "layout": None,
        "lines": [],
        "max_lines": 500,
    }

    def _pane_append(line: str) -> None:
        if not pane_state["enabled"]:
            return
        if line is None:
            return
        s = str(line)
        if not s:
            return
        # Split to keep rendering stable
        parts = s.splitlines() or [s]
        pane_state["lines"].extend(parts)
        # Trim
        if len(pane_state["lines"]) > pane_state["max_lines"]:
            pane_state["lines"] = pane_state["lines"][-pane_state["max_lines"] :]

    def _pane_update_chat_panel() -> None:
        if not pane_state["enabled"]:
            return
        live = pane_state.get("live")
        layout = pane_state.get("layout")
        if not live or not layout:
            return
        try:
            from rich.panel import Panel
            from rich.text import Text
            from rich.cells import cell_len
            from rich import box

            # Auto-follow: render only the bottom-most lines that fit in the panel.
            # (If we render the whole buffer, Rich will show from the top and the latest
            # conversation scrolls out of view.)
            try:
                chat_w = max(20, int(getattr(layout["chat"], "size", None).width or console.size.width) - 4)
                chat_h = max(6, int(getattr(layout["chat"], "size", None).height or console.size.height) - 4)
            except Exception:
                chat_w = max(20, console.size.width - 4)
                chat_h = max(6, console.size.height - 4)

            # Build visible lines from bottom up, accounting for wrapping.
            visible_lines = []
            used_rows = 0
            for ln in reversed(pane_state["lines"][-pane_state["max_lines"] :]):
                try:
                    t = Text.from_markup(ln)
                    plain = t.plain
                except Exception:
                    plain = str(ln)
                # Approximate wrap rows (cell_len accounts for CJK double-width chars)
                rows = max(1, (cell_len(plain) + max(1, chat_w) - 1) // max(1, chat_w))
                if used_rows + rows > chat_h:
                    break
                visible_lines.append(ln)
                used_rows += rows
            visible_lines.reverse()

            text = Text()
            for ln in visible_lines:
                try:
                    text.append_text(Text.from_markup(ln))
                except Exception:
                    text.append(ln)
                text.append("\n")

            layout["chat"].update(
                Panel(
                    text,
                    title="Chat",
                    border_style=theme_config.status,
                    box=box.ROUNDED,
                )
            )
            live.refresh()
        except Exception as e:
            import logging
            logging.getLogger("open_entity.cli").debug("pane render error: %s", e, exc_info=True)
            return

    def _pane_update_todo_panel(session_id: Optional[str]) -> None:
        if not pane_state["enabled"]:
            return
        live = pane_state.get("live")
        layout = pane_state.get("layout")
        if not live or not layout:
            return
        try:
            from rich.panel import Panel
            from rich.text import Text
            from rich import box
            from open_entity.tools.todo import todoread_all, set_current_session

            if session_id:
                set_current_session(session_id)
            raw = todoread_all()
            todo_text = Text(raw or "(no todos)", style="default")
            layout["todo"].update(
                Panel(
                    todo_text,
                    title="Todos",
                    border_style=theme_config.tools,
                    box=box.ROUNDED,
                )
            )
            live.refresh()
        except Exception as e:
            try:
                from rich.panel import Panel
                from rich.text import Text
                from rich import box

                layout["todo"].update(
                    Panel(
                        Text(f"(todo pane error) {e}", style="dim"),
                        title="Todos",
                        border_style=theme_config.tools,
                        box=box.ROUNDED,
                    )
                )
                live.refresh()
            except Exception:
                return

    # Streaming callback for CLI:
    # - tool/delegate logs are printed elsewhere (keep as-is)
    # - print streamed chunks only for orchestrator by default
    def progress_callback(
        event_type: str,
        content: str = None,
        agent_name: str = None,
        **kwargs
    ):
        """
        CLI progress callback.

        Notes:
        - We keep chunk streaming behavior as-is.
        - We additionally surface tool/delegate completion so users can see whether
          write_file/edit_file actually succeeded (or failed).
        """
        # ANSI color code mapping for async-input mode
        _ANSI_COLORS = {
            "black": "30", "red": "31", "green": "32", "yellow": "33",
            "blue": "34", "magenta": "35", "cyan": "36", "white": "37",
            "bright_black": "90", "bright_red": "91", "bright_green": "92",
            "bright_yellow": "93", "bright_blue": "94", "bright_magenta": "95",
            "bright_cyan": "96", "bright_white": "97", "grey50": "90",
        }

        def _get_ansi_code(style: str) -> str:
            """Extract ANSI code from Rich style string."""
            codes = []
            if "bold" in style:
                codes.append("1")
            for color_name, code in _ANSI_COLORS.items():
                if color_name in style:
                    codes.append(code)
                    break
            return ";".join(codes) if codes else "0"

        def _safe_stream_print_styled(text: str, style: str) -> None:
            """Print streamed text with color without breaking streaming."""
            if not text:
                return
            try:
                from rich.text import Text
                if async_input:
                    # Use ANSI escape codes for color in async-input mode
                    ansi_code = _get_ansi_code(style)
                    if ansi_code and ansi_code != "0":
                        _safe_stream_print(f"\x1b[{ansi_code}m{text}\x1b[0m")
                    else:
                        _safe_stream_print(text)
                else:
                    console.print(Text(text, style=style), end="")
            except BrokenPipeError:
                return
            except OSError as e:
                if getattr(e, "errno", None) == 32:
                    return
                # ペーンモード中は raw print を避ける (Live レイアウトが崩れるため)
                if not pane_state["enabled"]:
                    _safe_stream_print(text)
            except Exception:
                if not pane_state["enabled"]:
                    _safe_stream_print(text)

        # Start marker for orchestrator output (helps distinguish from user input)
        if event_type == "start" and (agent_name or "") == "orchestrator":
            _status_line.reset()
            _active_status["text"] = ""
            _active_status["start_time"] = 0.0
            stream_state["thinking_shown"] = False  # Reset thinking flag for new response
            stream_state["thinking_ended"] = False
            if pane_state["enabled"]:
                _pane_append("[bold]🤖[/bold] ")
                _pane_update_chat_panel()
                return
            if stream_state.get("mid_line"):
                _safe_stream_print("\n")
                stream_state["mid_line"] = False
            _safe_stream_print_styled("🤖 ", f"bold {theme_config.result}")
            stream_state["mid_line"] = True
            return

        # Thinking/reasoning content
        if event_type == "thinking" and content:
            if pane_state["enabled"]:
                # Show thinking in pane with dimmed style
                if not stream_state.get("thinking_shown"):
                    _pane_append("[dim]💭 Thinking...[/dim]")
                    stream_state["thinking_shown"] = True
                # Don't show full thinking content in pane (too verbose)
                return
            if async_input and pt_ansi_print:
                # Async-input mode: existing behavior
                if not stream_state.get("thinking_shown"):
                    pt_ansi_print("\x1b[2m💭 Thinking...\x1b[0m")
                    stream_state["thinking_shown"] = True
                if verbose:
                    pt_ansi_print(f"\x1b[2m{content}\x1b[0m")
                return
            # Normal mode: ephemeral status line (non-verbose) or inline text (verbose)
            if verbose:
                if not stream_state.get("thinking_shown"):
                    console.print("[dim]💭 Thinking...[/dim]")
                    stream_state["thinking_shown"] = True
                console.print(f"[dim]{content}[/dim]", end="")
            else:
                if not stream_state.get("thinking_shown"):
                    if stream_state.get("mid_line"):
                        _safe_stream_print("\n")
                        stream_state["mid_line"] = False
                    _active_status["text"] = "⏳ Thinking..."
                    _active_status["start_time"] = time.time()
                    _status_line.show("⏳ Thinking...", _active_status["start_time"])
                    stream_state["thinking_shown"] = True
            return

        # Streamed text chunks
        if event_type == "chunk" and content:
            # End thinking display if it was shown
            if stream_state.get("thinking_shown") and not stream_state.get("thinking_ended"):
                if not pane_state["enabled"]:
                    _status_line.clear()  # Clear ephemeral thinking status
                    _active_status["text"] = ""
                stream_state["thinking_ended"] = True
            name = agent_name or ""
            if name == "orchestrator" or stream_flags.get("show_subagent_stream"):
                if pane_state["enabled"]:
                    # Append to last line (create if needed)
                    if not pane_state["lines"]:
                        pane_state["lines"].append("🤖 ")
                    chunk = str(content)
                    parts = chunk.split("\n")
                    # First part appends to current last line
                    pane_state["lines"][-1] = (pane_state["lines"][-1] or "") + parts[0]
                    # Remaining parts become new lines
                    for p in parts[1:]:
                        pane_state["lines"].append(p)
                    # Trim
                    if len(pane_state["lines"]) > pane_state["max_lines"]:
                        pane_state["lines"] = pane_state["lines"][-pane_state["max_lines"] :]
                    _pane_update_chat_panel()
                    return
                # Normal mode: clear ephemeral status, print chunk, re-show status
                _status_line.clear()
                _safe_stream_print_styled(content, theme_config.result)
                stream_state["mid_line"] = True
                if _active_status["text"]:
                    _status_line.show(_active_status["text"], _active_status["start_time"])
            return

        # Ensure newline after orchestrator main response
        if event_type == "done":
            if (agent_name or "") == "orchestrator":
                _status_line.reset()
                _active_status["text"] = ""
                _active_status["start_time"] = 0.0
                if pane_state["enabled"]:
                    _pane_append("")  # spacing
                    _pane_update_chat_panel()
                    return
                _safe_stream_print("\n")
                stream_state["mid_line"] = False
            return

        # Delegation status (running/completed)
        if event_type == "delegate":
            if not stream_flags.get("show_tool_status", True):
                return
            status = (kwargs.get("status") or "").lower()
            name = kwargs.get("name") or agent_name or ""
            detail = (kwargs.get("detail") or "").strip()
            if name and not str(name).startswith("@"):
                name = f"@{name}"
            if pane_state["enabled"]:
                # Keep default output compact: show only completion unless verbose.
                if status == "running" and verbose:
                    _pane_append(f"[dim]→ {name}[/dim]")
                elif status == "completed":
                    _pane_append(f"[green]✓ {name}[/green]")
                else:
                    if verbose:
                        _pane_append(f"[dim]{status or 'delegate'} {name}[/dim]")
                _pane_update_chat_panel()
                return
            # If we're mid-stream, start a fresh line to keep logs readable.
            if stream_state.get("mid_line"):
                _status_line.clear()
                _safe_stream_print("\n")
                stream_state["mid_line"] = False
            if async_input and pt_ansi_print:
                # Async-input mode: existing behavior (permanent lines)
                if status == "running":
                    msg = f"\x1b[2m→\x1b[0m \x1b[36m{name}\x1b[0m"
                    if detail:
                        d = detail.replace("\n", " ").strip()
                        if len(d) > 90:
                            d = d[:87] + "..."
                        msg += f" \x1b[2m{d}\x1b[0m"
                    pt_ansi_print(msg)
                elif status == "completed":
                    pt_ansi_print(f"\x1b[32m✓\x1b[0m \x1b[36m{name}\x1b[0m")
                else:
                    pt_ansi_print(f"\x1b[2m{status or 'delegate'}\x1b[0m \x1b[36m{name}\x1b[0m")
                return
            # Normal mode: ephemeral status line for running, metrics on completion
            if status == "running":
                d = detail.replace("\n", " ").strip() if detail else ""
                if len(d) > 80:
                    d = d[:77] + "..."
                status_text = f"⏳ {name}: {d}" if d else f"⏳ {name}"
                _active_status["text"] = status_text
                _active_status["start_time"] = kwargs.get("start_time", time.time())
                _status_line.show(status_text, _active_status["start_time"])
            elif status == "completed":
                _status_line.clear()
                _active_status["text"] = ""
                # Build metrics suffix
                metrics_parts = []
                exec_time_ms = kwargs.get("execution_time_ms", 0)
                tokens_in = kwargs.get("tokens_input", 0)
                tokens_out = kwargs.get("tokens_output", 0)
                tool_count = kwargs.get("tool_calls", 0)
                if exec_time_ms > 0:
                    secs = exec_time_ms / 1000.0
                    if secs >= 60:
                        mins = int(secs // 60)
                        remaining = secs % 60
                        metrics_parts.append(f"{mins}m {remaining:.0f}s")
                    else:
                        metrics_parts.append(f"{secs:.1f}s")
                total_tokens = tokens_in + tokens_out
                if total_tokens > 0:
                    if total_tokens >= 1000:
                        metrics_parts.append(f"{total_tokens / 1000:.1f}k tokens")
                    else:
                        metrics_parts.append(f"{total_tokens} tokens")
                if tool_count > 0:
                    metrics_parts.append(f"{tool_count} tools")
                metrics_str = " \u00b7 ".join(metrics_parts)
                if metrics_str:
                    console.print(f"[green]\u2713 {name}[/green] [dim]({metrics_str})[/dim]")
                else:
                    console.print(f"[green]\u2713 {name}[/green]")
            else:
                _status_line.clear()
                console.print(f"[dim]{status or 'delegate'} {name}[/dim]")
            return

        # Tool status: show running + success/error so file ops are verifiable in-chat.
        if event_type == "tool":
            if not stream_flags.get("show_tool_status", True):
                return
            status = (kwargs.get("status") or "").lower()
            tool_name = kwargs.get("tool_name") or kwargs.get("tool") or ""
            detail = kwargs.get("detail") or ""
            result = kwargs.get("result")

            if pane_state["enabled"]:
                # Default: one line per tool (completed only). Running line only in verbose.
                if status == "running":
                    if verbose:
                        line = tool_name or "tool"
                        if detail:
                            line += f" → {detail}"
                        _pane_append(f"[dim]→ {line}[/dim]")
                        _pane_update_chat_panel()
                    return
                if status != "completed":
                    return

                result_str = "" if result is None else str(result)
                is_error = result_str.startswith("Error") or result_str.startswith("ERROR:")
                line = tool_name or "tool"
                if detail:
                    line += f" → {detail}"
                # (No long summary here; keep compact. Verbose summary stays in normal mode.)
                if is_error:
                    _pane_append(f"[red]✗ {line}[/red]")
                else:
                    _pane_append(f"[green]✓ {line}[/green]")
                _pane_update_chat_panel()
                # Refresh todo pane immediately when todos might have changed.
                if tool_name in ("todowrite", "todoread", "todoread_all"):
                    _pane_update_todo_panel(command_context.get("session_id"))
                return

            if stream_state.get("mid_line"):
                _status_line.clear()
                _safe_stream_print("\n")
                stream_state["mid_line"] = False

            # Async-input mode: existing behavior (permanent lines)
            if async_input and pt_ansi_print:
                if status == "running":
                    if verbose:
                        line = tool_name or "tool"
                        if detail:
                            line += f" \u2192 {detail}"
                        pt_ansi_print(f"\x1b[2m\u2192\x1b[0m \x1b[36m{line}\x1b[0m")
                elif status == "completed":
                    result_str = "" if result is None else str(result)
                    is_error = result_str.startswith("Error") or result_str.startswith("ERROR:")
                    line = tool_name or "tool"
                    if detail:
                        line += f" \u2192 {detail}"
                    if is_error:
                        pt_ansi_print(f"\x1b[31m\u2717\x1b[0m \x1b[36m{line}\x1b[0m")
                    else:
                        pt_ansi_print(f"\x1b[32m\u2713\x1b[0m \x1b[36m{line}\x1b[0m")
                return

            # Normal mode: ephemeral status line for running, permanent for completed
            if status == "running":
                line = tool_name or "tool"
                if detail:
                    line += f" {detail}"
                status_text = f"\u23f3 {line}..."
                _active_status["text"] = status_text
                _active_status["start_time"] = time.time()
                _status_line.show(status_text, _active_status["start_time"])
                return

            if status != "completed":
                return

            _status_line.clear()
            _active_status["text"] = ""

            # Determine success/failure from result text
            result_str = "" if result is None else str(result)
            is_error = result_str.startswith("Error") or result_str.startswith("ERROR:")

            # Build a concise line
            line = tool_name or "tool"
            if detail:
                line += f" {detail}"
            if verbose and result_str:
                summary = result_str.splitlines()[0].strip()
                if len(summary) > 140:
                    summary = summary[:137] + "..."
                if summary:
                    line += f" ({summary})"

            if is_error:
                console.print(f"[red]\u2717 {line}[/red]")
            else:
                console.print(f"[dim]\u2713 {line}[/dim]")
            return

    # プロファイルの解決（指定なしの場合は対話選択）
    if profile is None:
        available_profiles = get_available_profiles()
        env_profile = os.environ.get("MOCO_PROFILE")
        if env_profile and env_profile in available_profiles:
            profile = env_profile
        elif "entity" in available_profiles:
            profile = "entity"
        elif len(available_profiles) == 1:
            profile = available_profiles[0]
        else:
            profile = prompt_profile_selection()

    # プロバイダーの解決（指定なしの場合は優先順位で自動選択）
    if provider is None:
        provider = get_available_provider()

    provider_enum, model = resolve_provider(provider, model)
    # デフォルトのストリーム挙動:
    # - ZAI: ツール呼び出しがストリーミングで不安定なためデフォルトOFF
    # - その他: デフォルトON
    # NOTE: LLMProvider is a simple constants class (strings), not Enum.
    provider_name = getattr(provider_enum, "value", provider_enum)
    if stream is None:
        stream = (provider_name != "zai")

    with console.status(f"[bold cyan]Initializing Orchestrator ({profile})...[/]"):
        o = Orchestrator(
            profile=profile,
            provider=provider_enum,
            model=model,
            stream=stream,
            verbose=verbose,
            use_optimizer=use_optimizer,
            progress_callback=progress_callback if stream else None,
        )

    # Context for slash commands
    command_context = {
        'orchestrator': o,
        'console': console,
        'verbose': verbose,
        'stream_flags': stream_flags,
    }

    # セッション管理
    session_id = None
    if not new_session:
        if session:
            # 名前付きセッションを検索
            sessions = o.session_logger.list_sessions(limit=50)
            for s in sessions:
                if s.get("title", "").endswith(f"[{session}]"):
                    session_id = s.get("session_id")
                    console.print(f"[dim]Resuming session: {session}[/dim]")
                    break
        else:
            # 最新のセッションを取得（デフォルトの挙動）
            sessions = o.session_logger.list_sessions(limit=1)
            if sessions:
                session_id = sessions[0].get("session_id")
                console.print(f"[dim]Using latest session: {session_id[:8]}...[/dim]")

    if not session_id:
        title = "CLI Chat" + (f" [{session}]" if session else "")
        session_id = o.create_session(title=title)
        console.print(f"[dim]New session: {session_id[:8]}...[/dim]")

    command_context['session_id'] = session_id
    # Optional: allow slash commands to interact with the todo-pane
    # (so `/todo` can refresh the right pane without printing raw text to the terminal).
    command_context["pane_enabled"] = bool(pane_state.get("enabled"))
    command_context["pane_append"] = _pane_append
    command_context["pane_refresh_chat"] = _pane_update_chat_panel
    command_context["pane_refresh_todo"] = lambda: _pane_update_todo_panel(command_context.get("session_id"))

    # --- Dashboard Display ---
    from .ui.welcome import show_welcome_dashboard
    show_welcome_dashboard(o, theme_config)
    # -------------------------

    # If todo pane is enabled, set up a 2-pane Rich layout
    live_ctx = None
    if todo_pane:
        try:
            from rich.layout import Layout
            from rich.live import Live
            from rich.panel import Panel
            from rich.text import Text
            from rich import box
            from open_entity.tools.todo import set_current_session

            set_current_session(session_id)

            root = Layout(name="root")
            width = getattr(console, "size", None).width if getattr(console, "size", None) else 120

            if width >= 120:
                root.split_row(
                    Layout(name="chat", ratio=3),
                    Layout(name="todo", ratio=1, minimum_size=36),
                )
            else:
                # Fallback for narrow terminals: place todo below
                root.split_column(
                    Layout(name="chat", ratio=3),
                    Layout(name="todo", ratio=1),
                )

            pane_state["enabled"] = True
            pane_state["layout"] = root

            # Initial render
            root["chat"].update(
                Panel(Text("(waiting for output...)", style="dim"), title="Chat", border_style=theme_config.status, box=box.ROUNDED)
            )
            root["todo"].update(
                Panel(Text("(loading...)", style="dim"), title="Todos", border_style=theme_config.tools, box=box.ROUNDED)
            )

            live_ctx = Live(root, console=console, auto_refresh=False)
            live_ctx.__enter__()
            pane_state["live"] = live_ctx

            _pane_update_todo_panel(session_id)
            _pane_update_chat_panel()
        except Exception as e:
            pane_state["enabled"] = False
            pane_state["live"] = None
            pane_state["layout"] = None
            console.print(f"[yellow]Todo pane disabled (failed to initialize): {e}[/yellow]")

    # --- スラッシュコマンド対応 ---
    from .cli_commands import handle_slash_command
    from .cancellation import create_cancel_event, request_cancel, clear_cancel_event, OperationCancelled
    # ---

    try:
        # If async_input is enabled, run orchestration in a background worker and keep reading input.
        if async_input:
            try:
                from prompt_toolkit import PromptSession
                from prompt_toolkit.patch_stdout import patch_stdout
                from prompt_toolkit.key_binding import KeyBindings
            except Exception as e:
                console.print(f"[yellow]--async-input requires prompt_toolkit. ({e})[/yellow]")
                async_input = False

        if async_input:
            import threading
            import queue
            from datetime import datetime as _dt
            from prompt_toolkit.shortcuts import print_formatted_text
            from prompt_toolkit.formatted_text import ANSI

            # Tell slash commands to avoid Rich markup (prevents raw ANSI escapes in some terminals).
            command_context["plain_output"] = True
            command_context["plain_print"] = print_formatted_text

            # Use ANSI-aware printing for progress output (tool/delegate) to keep colors without mojibake.
            def _pt_ansi_print(s: str) -> None:
                try:
                    print_formatted_text(ANSI(s))
                except Exception:
                    # fall back to plain stdout
                    _safe_stream_print(str(s) + "\n")

            pt_ansi_print = _pt_ansi_print

            pending: "queue.Queue[str | None]" = queue.Queue()
            busy_lock = threading.Lock()
            busy = {"running": False}
            stop_requested = {"stop": False}

            def _set_busy(val: bool) -> None:
                with busy_lock:
                    busy["running"] = val

            def _is_busy() -> bool:
                with busy_lock:
                    return bool(busy["running"])

            def _worker() -> None:
                while True:
                    item = pending.get()
                    if item is None:
                        return

                    _set_busy(True)
                    try:
                        create_cancel_event(session_id)
                        result = o.run_sync(item, session_id)
                        if result and not stream:
                            # Prefer plain output in async-input mode to avoid ANSI artifacts.
                            print_formatted_text("")
                            print_formatted_text(result)
                            print_formatted_text("")
                    except KeyboardInterrupt:
                        request_cancel(session_id)
                        print_formatted_text("\nInterrupted.")
                    except OperationCancelled:
                        print_formatted_text("\nOperation cancelled.")
                    except Exception as e:  # noqa: BLE001
                        print_formatted_text(f"Error: {e}")
                    finally:
                        clear_cancel_event(session_id)
                        _set_busy(False)
                        if stop_requested["stop"]:
                            return

            worker = threading.Thread(target=_worker, daemon=True)
            worker.start()

            kb = KeyBindings()

            @kb.add("c-c")
            def _(event):  # noqa: ANN001
                # If running, cancel current task; otherwise exit.
                if _is_busy():
                    request_cancel(session_id)
                    print_formatted_text("(cancel requested)")
                else:
                    stop_requested["stop"] = True
                    pending.put(None)
                    event.app.exit()

            prompt = PromptSession(key_bindings=kb)

            with patch_stdout():
                while True:
                    # 最新のテーマ設定を反映
                    theme_config = THEMES[ui_state.theme]

                    try:
                        text = prompt.prompt("> ")
                    except (EOFError, KeyboardInterrupt):
                        # EOF / Ctrl+C while idle -> exit
                        stop_requested["stop"] = True
                        pending.put(None)
                        break

                    if not (text or "").strip():
                        continue

                    # Slash commands are processed immediately in the main thread.
                    if text.strip().startswith("/"):
                        # Avoid session-changing commands while busy (they can desync current run)
                        if _is_busy() and text.strip().split()[0].lower() in ("/profile", "/session", "/clear"):
                            print_formatted_text("That command is blocked while a task is running. Try again after completion.")
                            continue

                        if not handle_slash_command(text, command_context):
                            stop_requested["stop"] = True
                            pending.put(None)
                            break

                        if "pending_prompt" in command_context:
                            text = command_context.pop("pending_prompt")
                        else:
                            session_id = command_context["session_id"]
                            continue

                    lowered = text.strip().lower()
                    if lowered in ("exit", "quit"):
                        stop_requested["stop"] = True
                        # Ask current run to stop, then exit after worker finishes.
                        if _is_busy():
                            request_cancel(session_id)
                        pending.put(None)
                        break

                    # Enqueue normal prompts.
                    pending.put(text)
                    qsize = pending.qsize()
                    if _is_busy() or qsize > 0:
                        # Plain text to avoid ANSI escape artifacts in some terminals/recorders
                        print_formatted_text(f"(queued {qsize} @ {_dt.now().strftime('%H:%M:%S')})")

            # Wait briefly for worker to exit (best-effort)
            worker.join(timeout=2)
            return

        while True:
            # 最新のテーマ設定を反映
            theme_config = THEMES[ui_state.theme]

            try:
                if pane_state["enabled"]:
                    _pane_update_todo_panel(command_context.get("session_id"))
                    _pane_update_chat_panel()
                # Liveが有効だと入力プロンプトが再描画で見えなくなるので、
                # 入力中は一時的に Live を停止して端末の制御を戻す。
                if pane_state["enabled"] and live_ctx is not None:
                    try:
                        live_ctx.stop()
                    except Exception:
                        # stop() が途中で失敗した場合、カーソルを復元して端末を安定させる
                        try:
                            console.file.write("\x1b[?25h")
                            console.file.flush()
                        except Exception:
                            pass

                text = console.input(f"[bold {theme_config.status}]> [/bold {theme_config.status}]")

                # 入力が終わったら Live を再開し、左ペインにもユーザー入力を残す
                if pane_state["enabled"] and live_ctx is not None:
                    try:
                        live_ctx.start()
                    except Exception:
                        # Live の再開に失敗した場合、ペーンモードを無効にして通常モードに切り替え
                        pane_state["enabled"] = False
                        pane_state["live"] = None
                        console.print("[yellow]Todo pane disabled (display error). Chat continues normally.[/yellow]")
                    if text and text.strip():
                        _pane_append(f"[bold {theme_config.status}]User:[/bold {theme_config.status}] {text.strip()}")
                        _pane_update_chat_panel()
            except EOFError:
                break

            if not text.strip():
                continue

            # スラッシュコマンド判定
            if text.strip().startswith('/'):
                if not handle_slash_command(text, command_context):
                    raise typer.Exit(code=0)

                # カスタムコマンド等で pending_prompt がセットされた場合、それを通常の入力として扱う
                if 'pending_prompt' in command_context:
                    text = command_context.pop('pending_prompt')
                else:
                    # handle_slash_command 内で session_id が更新されている可能性がある
                    session_id = command_context['session_id']
                    continue

            lowered = text.strip().lower()
            if lowered in ("exit", "quit"):
                console.print("[dim]Bye![/dim]")
                raise typer.Exit(code=0)

            try:
                create_cancel_event(session_id)
                # シンプルにrun_syncを呼ぶだけ（streaming時はruntimeが直接出力）
                reply = o.run_sync(text, session_id)
            except KeyboardInterrupt:
                _status_line.reset()
                request_cancel(session_id)
                console.print("\n[yellow]Interrupted. Type 'exit' to quit or continue with a new prompt.[/yellow]")
                continue
            except OperationCancelled:
                _status_line.reset()
                console.print("\n[yellow]Operation cancelled.[/yellow]")
                continue
            except Exception as e:  # noqa: BLE001
                _status_line.reset()
                console.print(f"[red]Error: {e}[/red]")
                continue
            finally:
                clear_cancel_event(session_id)

            # stream 時は Live または runtime の標準出力で表示済み（ここで二重表示しない）
            if reply and not stream:
                console.print()
                _print_result(console, reply, theme_name=ui_state.theme, verbose=verbose)
                console.print()
    except KeyboardInterrupt:
        _status_line.reset()
        console.print("\n[dim]Bye![/dim]")
    finally:
        if live_ctx is not None:
            try:
                live_ctx.__exit__(None, None, None)
            except Exception:
                pass








@app.command()
def ui(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="ホストアドレス"),
    port: int = typer.Option(8000, "--port", "-p", help="ポート番号"),
    reload: bool = typer.Option(False, "--reload", "-r", help="開発モード（自動リロード）"),
    profile: str = typer.Option(None, "--profile", "-P", help="使用するプロファイル (例: entity)"),
):
    """Web UI を起動"""
    import uvicorn
    from rich.console import Console
    
    # プロファイルが指定された場合、環境変数を設定
    if profile:
        os.environ["MOCO_PROFILE"] = profile
    
    console = Console()
    active_profile = os.environ.get("MOCO_PROFILE", "default")
    console.print(f"\n🚀 [bold cyan]Moco Web UI[/bold cyan] starting... (profile: {active_profile})")
    console.print(f"   URL: [link]http://{host if host != '0.0.0.0' else 'localhost'}:{port}[/link]\n")
    
    uvicorn.run(
        "open_entity.ui.api:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )


def main():
    app()


if __name__ == "__main__":
    main()
