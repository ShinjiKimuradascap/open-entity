#!/usr/bin/env python3
"""
Wallet Manager CLI
コマンドラインからウォレットを管理するツール

Usage:
    python wallet_cli.py create [--path PATH] [--password PASSWORD]
    python wallet_cli.py load [--path PATH] [--password PASSWORD]
    python wallet_cli.py delete [--path PATH] [--force]
    python wallet_cli.py status [--path PATH]
    python wallet_cli.py export-pubkey [--path PATH] [--password PASSWORD] [--output FILE]
"""

import argparse
import sys
import os
import getpass
import json

# servicesディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crypto import WalletManager


DEFAULT_WALLET_PATH = os.path.expanduser("~/.peer_service/wallet.json")


def get_password(prompt: str = "Password: ") -> str:
    """パスワードを安全に入力"""
    return getpass.getpass(prompt)


def cmd_create(args):
    """ウォレット作成コマンド"""
    wallet_path = args.path or DEFAULT_WALLET_PATH
    
    wallet = WalletManager(wallet_path)
    
    if wallet.wallet_exists():
        print(f"❌ Error: Wallet already exists at {wallet_path}")
        print("   Use 'delete' command first if you want to recreate.")
        return 1
    
    # パスワード入力
    if args.password:
        password = args.password
    else:
        password = get_password("Enter password for new wallet: ")
        confirm = get_password("Confirm password: ")
        if password != confirm:
            print("❌ Error: Passwords do not match")
            return 1
    
    if not password:
        print("❌ Error: Password cannot be empty")
        return 1
    
    try:
        priv_key, pub_key = wallet.create_wallet(password)
        print(f"✅ Wallet created successfully!")
        print(f"   Location: {wallet_path}")
        print(f"   Public Key: {pub_key[:32]}...{pub_key[-8:]}")
        print(f"   \n⚠️  IMPORTANT: Keep your password safe. Without it, your wallet cannot be recovered.")
        return 0
    except Exception as e:
        print(f"❌ Error creating wallet: {e}")
        return 1


def cmd_load(args):
    """ウォレット読み込みコマンド"""
    wallet_path = args.path or DEFAULT_WALLET_PATH
    
    wallet = WalletManager(wallet_path)
    
    if not wallet.wallet_exists():
        print(f"❌ Error: Wallet not found at {wallet_path}")
        return 1
    
    password = args.password or get_password("Enter password: ")
    
    try:
        priv_key, pub_key = wallet.load_wallet(password)
        print(f"✅ Wallet loaded successfully!")
        print(f"   Public Key: {pub_key}")
        print(f"   Private Key: {priv_key[:16]}...{priv_key[-16:]} (hidden)")
        
        if args.verbose:
            print(f"\n   Full Public Key:\n   {pub_key}")
        
        return 0
    except ValueError as e:
        print(f"❌ Error: Invalid password")
        return 1
    except Exception as e:
        print(f"❌ Error loading wallet: {e}")
        return 1


def cmd_delete(args):
    """ウォレット削除コマンド"""
    wallet_path = args.path or DEFAULT_WALLET_PATH
    
    wallet = WalletManager(wallet_path)
    
    if not wallet.wallet_exists():
        print(f"❌ Error: Wallet not found at {wallet_path}")
        return 1
    
    if not args.force:
        confirm = input(f"⚠️  Are you sure you want to delete the wallet at {wallet_path}? [yes/no]: ")
        if confirm.lower() != "yes":
            print("Cancelled.")
            return 0
    
    try:
        wallet.delete_wallet()
        print(f"✅ Wallet deleted successfully!")
        return 0
    except Exception as e:
        print(f"❌ Error deleting wallet: {e}")
        return 1


def cmd_status(args):
    """ウォレット状態確認コマンド"""
    wallet_path = args.path or DEFAULT_WALLET_PATH
    
    wallet = WalletManager(wallet_path)
    
    print(f"Wallet Status:")
    print(f"   Path: {wallet_path}")
    print(f"   Exists: {'✅ Yes' if wallet.wallet_exists() else '❌ No'}")
    
    if wallet.wallet_exists():
        try:
            with open(wallet_path, 'r') as f:
                data = json.load(f)
            print(f"   Version: {data.get('version', 'unknown')}")
            print(f"   Public Key: {data.get('public_key', 'N/A')[:32]}...")
            
            # ファイルパーミッション確認
            import stat
            file_stat = os.stat(wallet_path)
            file_mode = stat.S_IMODE(file_stat.st_mode)
            print(f"   Permissions: {oct(file_mode)} (expected: 0o600)")
        except Exception as e:
            print(f"   Error reading wallet: {e}")
    
    return 0


def cmd_export_pubkey(args):
    """公開鍵をエクスポートするコマンド"""
    wallet_path = args.path or DEFAULT_WALLET_PATH
    
    wallet = WalletManager(wallet_path)
    
    if not wallet.wallet_exists():
        print(f"❌ Error: Wallet not found at {wallet_path}")
        return 1
    
    password = args.password or get_password("Enter password: ")
    
    try:
        priv_key, pub_key = wallet.load_wallet(password)
        
        if args.output:
            with open(args.output, 'w') as f:
                json.dump({
                    "public_key": pub_key,
                    "export_date": str(os.path.getmtime(wallet_path))
                }, f, indent=2)
            print(f"✅ Public key exported to {args.output}")
        else:
            print(pub_key)
        
        return 0
    except ValueError as e:
        print(f"❌ Error: Invalid password")
        return 1
    except Exception as e:
        print(f"❌ Error exporting public key: {e}")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="Wallet Manager CLI - Manage your AI agent wallet",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s create                          # Create wallet at default location
    %(prog)s create --path ./my_wallet.json  # Create wallet at specific path
    %(prog)s load                            # Load wallet
    %(prog)s status                          # Check wallet status
    %(prog)s delete                          # Delete wallet (with confirmation)
    %(prog)s delete --force                  # Delete wallet without confirmation
    %(prog)s export-pubkey                   # Export public key
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # create command
    create_parser = subparsers.add_parser("create", help="Create a new wallet")
    create_parser.add_argument("--path", "-p", help="Wallet file path")
    create_parser.add_argument("--password", help="Password (will prompt if not provided)")
    
    # load command
    load_parser = subparsers.add_parser("load", help="Load an existing wallet")
    load_parser.add_argument("--path", "-p", help="Wallet file path")
    load_parser.add_argument("--password", help="Password (will prompt if not provided)")
    load_parser.add_argument("--verbose", "-v", action="store_true", help="Show full public key")
    
    # delete command
    delete_parser = subparsers.add_parser("delete", help="Delete a wallet")
    delete_parser.add_argument("--path", "-p", help="Wallet file path")
    delete_parser.add_argument("--force", "-f", action="store_true", help="Delete without confirmation")
    
    # status command
    status_parser = subparsers.add_parser("status", help="Check wallet status")
    status_parser.add_argument("--path", "-p", help="Wallet file path")
    
    # export-pubkey command
    export_parser = subparsers.add_parser("export-pubkey", help="Export public key")
    export_parser.add_argument("--path", "-p", help="Wallet file path")
    export_parser.add_argument("--password", help="Password (will prompt if not provided)")
    export_parser.add_argument("--output", "-o", help="Output file (default: stdout)")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # コマンド実行
    commands = {
        "create": cmd_create,
        "load": cmd_load,
        "delete": cmd_delete,
        "status": cmd_status,
        "export-pubkey": cmd_export_pubkey,
    }
    
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
