#!/usr/bin/env python3
"""
Email Sending Tool
==================
コマンドラインからメールを送信するツール

Usage:
    # テキストメール送信
    python tools/send_email.py to@example.com "件名" "本文"
    
    # HTMLメール送信
    python tools/send_email.py to@example.com "件名" "<h1>HTML本文</h1>" --html
    
    # 複数宛先
    python tools/send_email.py to1@example.com,to2@example.com "件名" "本文"
    
    # CC/BCC付き
    python tools/send_email.py to@example.com "件名" "本文" --cc cc@example.com --bcc bcc@example.com

Environment:
    GMAIL_CREDENTIALS_PATH: Service Account認証情報ファイルのパス
"""

import sys
import os
import argparse
import logging
from pathlib import Path

# 親ディレクトリをPythonパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from skills.gmail import GmailClient, GmailClientError

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def parse_arguments() -> argparse.Namespace:
    """コマンドライン引数をパース"""
    parser = argparse.ArgumentParser(
        description='メール送信ツール',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s recipient@example.com "テスト件名" "テスト本文"
  %(prog)s user1@example.com,user2@example.com "件名" "本文" --html
  %(prog)s to@example.com "件名" "本文" --cc cc@example.com --bcc bcc@example.com
        """
    )
    
    parser.add_argument(
        'to',
        help='宛先メールアドレス（複数の場合はカンマ区切り）'
    )
    
    parser.add_argument(
        'subject',
        help='メール件名'
    )
    
    parser.add_argument(
        'body',
        help='メール本文'
    )
    
    parser.add_argument(
        '--html',
        action='store_true',
        help='HTMLメールとして送信'
    )
    
    parser.add_argument(
        '--cc',
        help='CC宛先（カンマ区切りで複数指定可能）'
    )
    
    parser.add_argument(
        '--bcc',
        help='BCC宛先（カンマ区切りで複数指定可能）'
    )
    
    parser.add_argument(
        '--from',
        dest='sender',
        help='送信者メールアドレス（未指定時はService Accountのメール）'
    )
    
    parser.add_argument(
        '--credentials',
        default=os.getenv('GMAIL_CREDENTIALS_PATH', 'config/gmail_credentials.json'),
        help='Service Account認証情報ファイルのパス'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='実際には送信せず、送信内容を表示のみ'
    )
    
    return parser.parse_args()


def main() -> int:
    """メイン処理"""
    args = parse_arguments()
    
    # 宛先をパース
    to_addresses = [addr.strip() for addr in args.to.split(',')]
    
    # CCをパース
    cc_addresses = None
    if args.cc:
        cc_addresses = [addr.strip() for addr in args.cc.split(',')]
    
    # BCCをパース
    bcc_addresses = None
    if args.bcc:
        bcc_addresses = [addr.strip() for addr in args.bcc.split(',')]
    
    # 本文タイプ
    body_type = 'html' if args.html else 'text'
    
    # Dry runモード
    if args.dry_run:
        print("=== Dry Run Mode ===")
        print(f"To: {', '.join(to_addresses)}")
        print(f"Subject: {args.subject}")
        print(f"Body Type: {body_type}")
        if cc_addresses:
            print(f"CC: {', '.join(cc_addresses)}")
        if bcc_addresses:
            print(f"BCC: {', '.join(bcc_addresses)}")
        if args.sender:
            print(f"From: {args.sender}")
        print(f"Credentials: {args.credentials}")
        print("\nBody:")
        print(args.body)
        return 0
    
    try:
        # クライアント初期化
        logger.info(f"Gmailクライアントを初期化: {args.credentials}")
        client = GmailClient(args.credentials)
        
        # メール送信
        logger.info(f"メール送信: {', '.join(to_addresses)}")
        result = client.send_email(
            to=to_addresses,
            subject=args.subject,
            body=args.body,
            body_type=body_type,
            cc=cc_addresses,
            bcc=bcc_addresses,
            sender=args.sender
        )
        
        # 結果表示
        print("✅ メール送信成功")
        print(f"   Message ID: {result['message_id']}")
        print(f"   Thread ID: {result['thread_id']}")
        
        return 0
        
    except GmailClientError as e:
        logger.error(f"Gmailエラー: {e}")
        print(f"❌ エラー: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        logger.error(f"予期しないエラー: {e}")
        print(f"❌ 予期しないエラー: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
