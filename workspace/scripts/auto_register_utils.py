#!/usr/bin/env python3
"""
自動登録スクリプト共通ユーティリティ

各クラウドサービス（PythonAnywhere, Render, Railway等）の自動登録で
使用する共通機能を提供します。
"""

import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, asdict

import requests


@dataclass
class RegistrationResult:
    """登録結果"""
    success: bool
    service: str
    username: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    credentials_file: Optional[Path] = None
    error_message: Optional[str] = None
    verification_required: bool = False
    verification_link: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        result = asdict(self)
        # Pathオブジェクトを文字列に変換
        if result.get('credentials_file'):
            result['credentials_file'] = str(result['credentials_file'])
        return result


class MailTMClient:
    """mail.tm APIクライアント"""
    
    API_BASE = "https://api.mail.tm"
    
    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    
    def get_messages(self, page: int = 1) -> List[Dict[str, Any]]:
        """メッセージ一覧を取得"""
        try:
            response = requests.get(
                f"{self.API_BASE}/messages",
                headers=self.headers,
                params={"page": page},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            return data.get("hydra:member", [])
        except Exception as e:
            print(f"[mail.tm] メッセージ取得エラー: {e}")
            return []
    
    def get_message(self, message_id: str) -> Dict[str, Any]:
        """特定のメッセージを取得"""
        try:
            response = requests.get(
                f"{self.API_BASE}/messages/{message_id}",
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"[mail.tm] メッセージ詳細取得エラー: {e}")
            return {}
    
    def delete_message(self, message_id: str) -> bool:
        """メッセージを削除"""
        try:
            response = requests.delete(
                f"{self.API_BASE}/messages/{message_id}",
                headers=self.headers,
                timeout=30
            )
            return response.status_code == 204
        except Exception as e:
            print(f"[mail.tm] メッセージ削除エラー: {e}")
            return False
    
    def get_account_info(self) -> Dict[str, Any]:
        """アカウント情報を取得"""
        try:
            response = requests.get(
                f"{self.API_BASE}/me",
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"[mail.tm] アカウント情報取得エラー: {e}")
            return {}
    
    def extract_verification_link(
        self,
        message: Dict[str, Any],
        service_patterns: Optional[List[str]] = None
    ) -> Optional[str]:
        """メッセージから認証リンクを抽出"""
        text = message.get("text", "")
        html = message.get("html", [])
        
        content = ""
        if html:
            content = html[0] if isinstance(html, list) else html
        else:
            content = text
        
        # デフォルトパターン
        default_patterns = [
            r'https?://[^\s"<>]*/confirm[^\s"<>]*',
            r'https?://[^\s"<>]*/verify[^\s"<>]*',
            r'https?://[^\s"<>]*/activate[^\s"<>]*',
            r'https?://[^\s"<>]*/magic[^\s"<>]*',
        ]
        
        patterns = service_patterns or default_patterns
        
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return match.group(0)
        
        return None
    
    async def wait_for_verification_email(
        self,
        service_keywords: List[str],
        max_wait_time: int = 300,
        poll_interval: int = 5,
        custom_patterns: Optional[List[str]] = None
    ) -> Optional[str]:
        """
        認証メールを待機してリンクを返す
        
        Args:
            service_keywords: サービス名のキーワードリスト（fromアドレスや件名に含まれる）
            max_wait_time: 最大待機時間（秒）
            poll_interval: ポーリング間隔（秒）
            custom_patterns: カスタム抽出パターン
        """
        print(f"[mail.tm] 認証メールを待機中... (最大{max_wait_time}秒)")
        
        waited = 0
        checked_ids = set()
        
        while waited < max_wait_time:
            messages = self.get_messages()
            
            for msg in messages:
                msg_id = msg.get("id")
                if msg_id in checked_ids:
                    continue
                checked_ids.add(msg_id)
                
                subject = msg.get("subject", "").lower()
                from_addr = msg.get("from", {}).get("address", "").lower()
                
                # サービスからのメールか確認
                is_target = any(kw.lower() in from_addr for kw in service_keywords) or \
                           any(kw.lower() in subject for kw in service_keywords)
                
                if is_target or any(kw in subject for kw in ["verify", "confirm", "activate", "magic"]):
                    print(f"[mail.tm] 認証メールを検出: {msg.get('subject', 'No Subject')}")
                    
                    message_detail = self.get_message(msg_id)
                    link = self.extract_verification_link(message_detail, custom_patterns)
                    
                    if link:
                        print(f"[mail.tm] 認証リンクを抽出: {link}")
                        return link
            
            await asyncio.sleep(poll_interval)
            waited += poll_interval
            
            if waited % 30 == 0:
                print(f"[mail.tm] 待機中... {waited}秒経過")
        
        print("[mail.tm] 認証メールが見つかりませんでした")
        return None


def save_credentials(
    service: str,
    credentials: Dict[str, Any],
    output_dir: Optional[Path] = None
) -> Path:
    """
    認証情報をJSONファイルに保存
    
    Args:
        service: サービス名
        credentials: 保存する認証情報
        output_dir: 出力ディレクトリ（省略時はデフォルト）
    
    Returns:
        保存したファイルのパス
    """
    if output_dir is None:
        output_dir = Path("/home/moco/workspace/data/credentials")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # ファイル名を生成
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if "username" in credentials and credentials["username"]:
        identifier = credentials["username"]
    elif "email" in credentials and credentials["email"]:
        identifier = credentials["email"].replace("@", "_at_").replace(".", "_")
    else:
        identifier = f"unknown_{timestamp}"
    
    output_file = output_dir / f"{service}_{identifier}.json"
    
    # メタデータを追加
    credentials["service"] = service
    credentials["created_at"] = datetime.now().isoformat()
    credentials["status"] = "active"
    
    with open(output_file, "w") as f:
        json.dump(credentials, f, indent=2, ensure_ascii=False)
    
    print(f"[Save] 認証情報を保存: {output_file}")
    return output_file


def load_credentials(service: str, identifier: str) -> Optional[Dict[str, Any]]:
    """保存された認証情報を読み込む"""
    cred_dir = Path("/home/moco/workspace/data/credentials")
    
    # ファイルを検索
    pattern = f"{service}_{identifier}*.json"
    files = list(cred_dir.glob(pattern))
    
    if not files:
        return None
    
    # 最新のファイルを読み込む
    latest_file = max(files, key=lambda p: p.stat().st_mtime)
    
    with open(latest_file, "r") as f:
        return json.load(f)


def list_saved_credentials() -> List[Dict[str, Any]]:
    """保存されている全認証情報を一覧表示"""
    cred_dir = Path("/home/moco/workspace/data/credentials")
    
    if not cred_dir.exists():
        return []
    
    credentials = []
    for file in cred_dir.glob("*.json"):
        try:
            with open(file, "r") as f:
                data = json.load(f)
                data["_file"] = str(file)
                credentials.append(data)
        except:
            pass
    
    return credentials


async def with_retry(
    func: Callable,
    max_retries: int = 3,
    retry_delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,)
) -> Any:
    """
    リトライ付きで関数を実行
    
    Args:
        func: 実行する関数
        max_retries: 最大リトライ回数
        retry_delay: 初回リトライまでの遅延（秒）
        backoff_factor: バックオフ係数
        exceptions: リトライ対象の例外
    
    Returns:
        関数の戻り値
    """
    last_exception = None
    delay = retry_delay
    
    for attempt in range(max_retries + 1):
        try:
            return await func() if asyncio.iscoroutinefunction(func) else func()
        except exceptions as e:
            last_exception = e
            if attempt < max_retries:
                print(f"[Retry] 試行{attempt + 1}/{max_retries + 1}失敗: {e}")
                print(f"[Retry] {delay}秒後にリトライ...")
                await asyncio.sleep(delay)
                delay *= backoff_factor
            else:
                print(f"[Retry] 最大リトライ回数に達しました")
    
    raise last_exception


def setup_proxy() -> Optional[Dict[str, str]]:
    """プロキシ設定を取得"""
    http_proxy = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
    https_proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
    
    if http_proxy or https_proxy:
        return {
            "http": http_proxy,
            "https": https_proxy or http_proxy
        }
    return None


def generate_secure_password(
    length: int = 20,
    include_upper: bool = True,
    include_lower: bool = True,
    include_digits: bool = True,
    include_special: bool = True
) -> str:
    """セキュアなパスワードを生成"""
    import secrets
    import string
    
    chars = ""
    if include_lower:
        chars += string.ascii_lowercase
    if include_upper:
        chars += string.ascii_uppercase
    if include_digits:
        chars += string.digits
    if include_special:
        chars += "!@#$%^&*-_+=."
    
    if not chars:
        raise ValueError("少なくとも1文字種を選択してください")
    
    return ''.join(secrets.choice(chars) for _ in range(length))


def mask_sensitive_info(text: str, visible_chars: int = 4) -> str:
    """機密情報をマスク表示"""
    if len(text) <= visible_chars * 2:
        return "*" * len(text)
    
    return text[:visible_chars] + "*" * (len(text) - visible_chars * 2) + text[-visible_chars:]


class RateLimiter:
    """レート制限対策用の簡易リミッター"""
    
    def __init__(self, min_interval: float = 1.0):
        self.min_interval = min_interval
        self.last_request = 0
    
    async def wait(self):
        """次のリクエストまで待機"""
        import time
        elapsed = time.time() - self.last_request
        if elapsed < self.min_interval:
            wait_time = self.min_interval - elapsed
            await asyncio.sleep(wait_time)
        self.last_request = time.time()


# 定数
DEFAULT_CREDENTIALS_DIR = Path("/home/moco/workspace/data/credentials")
DEFAULT_MAX_EMAIL_WAIT = 300  # 5分
DEFAULT_EMAIL_POLL_INTERVAL = 5  # 5秒


if __name__ == "__main__":
    # テスト実行
    print("[Utils] ユーティリティモジュールのテスト")
    
    # パスワード生成テスト
    pwd = generate_secure_password()
    print(f"生成パスワード: {mask_sensitive_info(pwd)}")
    
    # 認証情報保存テスト
    test_creds = {
        "username": "test_user",
        "email": "test@example.com",
        "password": "test_pass"
    }
    
    saved_file = save_credentials("test", test_creds, Path("/tmp/test_creds"))
    print(f"保存ファイル: {saved_file}")
    
    # 一覧取得テスト
    all_creds = list_saved_credentials()
    print(f"保存済み認証情報: {len(all_creds)}件")
