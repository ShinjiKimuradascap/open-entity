import json
import subprocess
from typing import List, Optional, Any, Dict

try:
    from ..utils.path import get_working_directory
except ImportError:
    # サブプロセスからロードされる場合のフォールバック
    from open_entity.utils.path import get_working_directory


def amp_cli(args: List[str], stdin: Optional[str] = None, timeout: int = 60) -> str:
    """
    amp CLI を直接実行します。

    Args:
        args: amp に渡す引数リスト（例: ["send", "--channel", "general", "--message", "Hello"]）
        stdin: 標準入力に渡す文字列（必要な場合のみ）
        timeout: タイムアウト秒（デフォルト 60）

    Returns:
        str: 実行結果（stdout + stderr）

    Examples:
        amp_cli(["--help"])
        amp_cli(["send", "--channel", "general", "--message", "Hello"])
    """
    if not isinstance(args, list) or not args or not all(isinstance(a, str) for a in args):
        return "Error: args must be a non-empty list of strings."

    # 乱用防止のため上限
    if len(args) > 50:
        return "Error: too many arguments for amp CLI."

    # タイムアウトの下限・上限
    try:
        timeout = int(timeout)
    except (TypeError, ValueError):
        timeout = 60
    timeout = max(1, min(timeout, 300))

    command = ["amp"] + args
    try:
        result = subprocess.run(
            command,
            input=stdin,
            text=True,
            capture_output=True,
            timeout=timeout,
            cwd=get_working_directory()
        )
    except FileNotFoundError:
        return "Error: amp CLI not found in PATH."
    except subprocess.TimeoutExpired:
        return f"Error: amp CLI timed out after {timeout}s."
    except Exception as e:
        return f"Error: amp CLI failed to run: {e}"

    output = result.stdout or ""
    if result.stderr:
        output += ("\nSTDERR:\n" + result.stderr)
    if result.returncode != 0:
        output += f"\nReturn Code: {result.returncode}"
    return output.strip() if output else "Command executed successfully (no output)."


def _append_flag(args: List[str], flag: str, value: Optional[Any]) -> None:
    if value is None:
        return
    args.extend([flag, str(value)])


def amp_send(
    to: str,
    message: str,
    gateway: Optional[str] = None,
    sender_id: Optional[str] = None,
    msg_type: str = "text",
    metadata: Optional[Any] = None,
    encrypt: bool = True,
    profile: Optional[str] = None,
    timeout: int = 60
) -> str:
    """
    amp の send コマンド用ショートカット。

    Args:
        to: 送信先エージェントID
        message: 送信メッセージ
        gateway: Gateway URL
        sender_id: 送信元エージェントID
        msg_type: メッセージタイプ（default: text）
        metadata: JSON 互換のメタデータ
        encrypt: E2E 暗号化（default: True）
        profile: amp プロファイル名
        timeout: タイムアウト秒
    """
    if not to or not message:
        return "Error: to and message are required."

    args = ["send", "--to", to]
    _append_flag(args, "--gateway", gateway)
    _append_flag(args, "--id", sender_id)
    if msg_type:
        _append_flag(args, "--type", msg_type)
    if metadata is not None:
        if isinstance(metadata, (dict, list)):
            metadata_str = json.dumps(metadata, ensure_ascii=False)
        else:
            metadata_str = str(metadata)
        _append_flag(args, "--metadata", metadata_str)
    if encrypt is False:
        args.append("--no-encrypt")
    _append_flag(args, "--profile", profile)
    args.append(message)
    return amp_cli(args, timeout=timeout)


def amp_history(limit: int = 50, gateway: Optional[str] = None, profile: Optional[str] = None, timeout: int = 60) -> str:
    """amp history のショートカット。"""
    args = ["history"]
    _append_flag(args, "--limit", limit)
    _append_flag(args, "--gateway", gateway)
    _append_flag(args, "--profile", profile)
    return amp_cli(args, timeout=timeout)


def amp_discover(local_only: bool = False, gateway: Optional[str] = None, profile: Optional[str] = None, timeout: int = 60) -> str:
    """amp discover のショートカット。"""
    args = ["discover"]
    if local_only:
        args.append("--local")
    _append_flag(args, "--gateway", gateway)
    _append_flag(args, "--profile", profile)
    return amp_cli(args, timeout=timeout)


def amp_identity_list(timeout: int = 60) -> str:
    """amp identity list のショートカット。"""
    return amp_cli(["identity", "list"], timeout=timeout)


def amp_identity_show(profile: Optional[str] = None, timeout: int = 60) -> str:
    """amp identity show のショートカット。"""
    args = ["identity", "show"]
    _append_flag(args, "--profile", profile)
    return amp_cli(args, timeout=timeout)


def amp_identity_create(
    name: str = "Anonymous",
    gateway: Optional[str] = None,
    profile: Optional[str] = None,
    timeout: int = 60
) -> str:
    """amp identity create のショートカット。"""
    args = ["identity", "create"]
    _append_flag(args, "--name", name)
    _append_flag(args, "--gateway", gateway)
    _append_flag(args, "--profile", profile)
    return amp_cli(args, timeout=timeout)


def amp_identity_import(
    private_key: str,
    name: str = "Imported",
    profile: Optional[str] = None,
    confirm: bool = False,
    timeout: int = 60
) -> str:
    """amp identity import のショートカット（秘密鍵を扱うので confirm=True 必須）。"""
    if not confirm:
        return "Error: confirm=True is required to import a private key."
    if not private_key:
        return "Error: private_key is required."
    args = ["identity", "import"]
    _append_flag(args, "--name", name)
    _append_flag(args, "--profile", profile)
    args.append(private_key)
    return amp_cli(args, timeout=timeout)


def amp_identity_use(profile: str, timeout: int = 60) -> str:
    """amp identity use のショートカット。"""
    if not profile:
        return "Error: profile is required."
    args = ["identity", "use"]
    _append_flag(args, "--profile", profile)
    return amp_cli(args, timeout=timeout)


def amp_identity_delete(
    profile: str,
    force: bool = False,
    confirm: bool = False,
    timeout: int = 60
) -> str:
    """amp identity delete のショートカット（破壊操作なので confirm=True 必須）。"""
    if not confirm:
        return "Error: confirm=True is required to delete an identity."
    if not profile:
        return "Error: profile is required."
    args = ["identity", "delete"]
    _append_flag(args, "--profile", profile)
    if force:
        args.append("--force")
    return amp_cli(args, timeout=timeout)


def amp_identity_export(
    profile: str,
    force: bool = False,
    confirm: bool = False,
    timeout: int = 60
) -> str:
    """amp identity export のショートカット（秘密鍵出力のため confirm=True 必須）。"""
    if not confirm:
        return "Error: confirm=True is required to export a private key."
    if not profile:
        return "Error: profile is required."
    args = ["identity", "export"]
    _append_flag(args, "--profile", profile)
    if force:
        args.append("--force")
    return amp_cli(args, timeout=timeout)


def amp_identity_reset(
    force: bool = False,
    profile: Optional[str] = None,
    confirm: bool = False,
    timeout: int = 60
) -> str:
    """amp identity reset のショートカット（破壊操作なので confirm=True 必須）。"""
    if not confirm:
        return "Error: confirm=True is required to reset identity."
    args = ["identity", "reset"]
    if force:
        args.append("--force")
    _append_flag(args, "--profile", profile)
    return amp_cli(args, timeout=timeout)
