"""
mail.tm API ラッパー
一時メールアドレスの作成・管理・メール受信機能を提供
"""

import requests
import time
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
from datetime import datetime

MAIL_TM_BASE_URL = "https://api.mail.tm"


@dataclass
class MailAccount:
    """メールアカウント情報"""
    address: str
    password: str
    token: Optional[str] = None
    id: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass
class EmailMessage:
    """メールメッセージ情報"""
    id: str
    from_address: str
    to_address: str
    subject: str
    intro: str
    text: Optional[str] = None
    html: Optional[str] = None
    created_at: Optional[datetime] = None
    seen: bool = False


class MailTMError(Exception):
    """mail.tm API エラー"""
    pass


class MailTMService:
    """
    mail.tm API サービスクラス
    
    認証不要で即座に使える一時メールアドレスを提供
    """
    
    def __init__(self, base_url: str = MAIL_TM_BASE_URL):
        self.base_url = base_url
        self._account: Optional[MailAccount] = None
    
    @property
    def account(self) -> Optional[MailAccount]:
        """現在のアカウント情報"""
        return self._account
    
    def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        APIリクエスト実行
        
        Args:
            method: HTTPメソッド
            endpoint: APIエンドポイント
            data: リクエストボディ
            headers: 追加ヘッダー
            token: 認証トークン
        
        Returns:
            APIレスポンス
        
        Raises:
            MailTMError: APIエラー時
        """
        url = f"{self.base_url}{endpoint}"
        request_headers = {"Content-Type": "application/json"}
        
        if headers:
            request_headers.update(headers)
        
        if token:
            request_headers["Authorization"] = f"Bearer {token}"
        
        try:
            response = requests.request(
                method=method,
                url=url,
                json=data,
                headers=request_headers,
                timeout=30
            )
            
            if response.status_code == 204:
                return {}
            
            if not response.ok:
                error_detail = ""
                try:
                    error_data = response.json()
                    error_detail = f": {error_data}"
                except:
                    error_detail = f": {response.text}"
                
                raise MailTMError(
                    f"API error {response.status_code}{error_detail}"
                )
            
            return response.json()
        
        except requests.exceptions.RequestException as e:
            raise MailTMError(f"Request failed: {e}")
    
    def get_domains(self) -> List[Dict[str, Any]]:
        """
        利用可能なドメイン一覧を取得
        
        Returns:
            ドメイン情報のリスト
        """
        response = self._request("GET", "/domains")
        return response.get("hydra:member", [])
    
    def create_account(
        self,
        address: Optional[str] = None,
        password: Optional[str] = None
    ) -> MailAccount:
        """
        一時メールアカウントを作成
        
        Args:
            address: メールアドレス（省略時は自動生成）
            password: パスワード（省略時はランダム生成）
        
        Returns:
            作成されたアカウント情報
        """
        import secrets
        import string
        
        # ドメインを取得
        domains = self.get_domains()
        if not domains:
            raise MailTMError("No domains available")
        
        domain = domains[0]["domain"]
        
        # アドレス生成
        if not address:
            random_string = ''.join(
                secrets.choice(string.ascii_lowercase + string.digits)
                for _ in range(10)
            )
            address = f"{random_string}@{domain}"
        
        # パスワード生成
        if not password:
            password = ''.join(
                secrets.choice(string.ascii_letters + string.digits)
                for _ in range(16)
            )
        
        # アカウント作成
        data = {
            "address": address,
            "password": password
        }
        
        response = self._request("POST", "/accounts", data=data)
        
        self._account = MailAccount(
            address=address,
            password=password,
            id=response.get("id"),
            created_at=datetime.now()
        )
        
        # トークン取得
        self._get_token()
        
        return self._account
    
    def _get_token(self) -> str:
        """
        認証トークンを取得
        
        Returns:
            アクセストークン
        
        Raises:
            MailTMError: アカウント未作成時
        """
        if not self._account:
            raise MailTMError("No account created")
        
        data = {
            "address": self._account.address,
            "password": self._account.password
        }
        
        response = self._request("POST", "/token", data=data)
        token = response.get("token")
        
        if not token:
            raise MailTMError("Failed to get token")
        
        self._account.token = token
        return token
    
    def get_messages(self, page: int = 1) -> List[EmailMessage]:
        """
        メール一覧を取得
        
        Args:
            page: ページ番号
        
        Returns:
            メールメッセージのリスト
        
        Raises:
            MailTMError: アカウント未作成時
        """
        if not self._account or not self._account.token:
            raise MailTMError("Not authenticated. Create account first.")
        
        params = f"?page={page}"
        response = self._request(
            "GET",
            f"/messages{params}",
            token=self._account.token
        )
        
        messages = []
        for msg_data in response.get("hydra:member", []):
            messages.append(EmailMessage(
                id=msg_data.get("id"),
                from_address=msg_data.get("from", {}).get("address", ""),
                to_address=msg_data.get("to", [{}])[0].get("address", ""),
                subject=msg_data.get("subject", ""),
                intro=msg_data.get("intro", ""),
                created_at=self._parse_datetime(msg_data.get("createdAt")),
                seen=msg_data.get("seen", False)
            ))
        
        return messages
    
    def get_message(self, message_id: str) -> EmailMessage:
        """
        メール詳細を取得
        
        Args:
            message_id: メッセージID
        
        Returns:
            メールメッセージの詳細
        
        Raises:
            MailTMError: アカウント未作成時またはメッセージ未存在時
        """
        if not self._account or not self._account.token:
            raise MailTMError("Not authenticated. Create account first.")
        
        response = self._request(
            "GET",
            f"/messages/{message_id}",
            token=self._account.token
        )
        
        return EmailMessage(
            id=response.get("id"),
            from_address=response.get("from", {}).get("address", ""),
            to_address=response.get("to", [{}])[0].get("address", ""),
            subject=response.get("subject", ""),
            intro=response.get("intro", ""),
            text=response.get("text"),
            html=response.get("html"),
            created_at=self._parse_datetime(response.get("createdAt")),
            seen=response.get("seen", False)
        )
    
    def delete_message(self, message_id: str) -> bool:
        """
        メールを削除
        
        Args:
            message_id: メッセージID
        
        Returns:
            削除成功時True
        
        Raises:
            MailTMError: アカウント未作成時
        """
        if not self._account or not self._account.token:
            raise MailTMError("Not authenticated. Create account first.")
        
        self._request(
            "DELETE",
            f"/messages/{message_id}",
            token=self._account.token
        )
        
        return True
    
    def delete_account(self) -> bool:
        """
        アカウントを削除
        
        Returns:
            削除成功時True
        
        Raises:
            MailTMError: アカウント未作成時
        """
        if not self._account or not self._account.token:
            raise MailTMError("No account to delete")
        
        self._request(
            "DELETE",
            f"/accounts/{self._account.id}",
            token=self._account.token
        )
        
        self._account = None
        return True
    
    def poll_for_messages(
        self,
        timeout: int = 60,
        interval: int = 5,
        max_messages: Optional[int] = None
    ) -> List[EmailMessage]:
        """
        メール受信をポーリング
        
        Args:
            timeout: タイムアウト秒数
            interval: ポーリング間隔秒数
            max_messages: 最大取得件数
        
        Returns:
            受信したメールリスト
        
        Raises:
            MailTMError: アカウント未作成時
        """
        if not self._account or not self._account.token:
            raise MailTMError("Not authenticated. Create account first.")
        
        start_time = time.time()
        seen_ids = set()
        new_messages = []
        
        while time.time() - start_time < timeout:
            messages = self.get_messages()
            
            for msg in messages:
                if msg.id not in seen_ids:
                    seen_ids.add(msg.id)
                    new_messages.append(msg)
                    
                    if max_messages and len(new_messages) >= max_messages:
                        return new_messages
            
            if new_messages:
                return new_messages
            
            time.sleep(interval)
        
        return new_messages
    
    def wait_for_message(
        self,
        subject_contains: Optional[str] = None,
        from_contains: Optional[str] = None,
        timeout: int = 120,
        interval: int = 5
    ) -> Optional[EmailMessage]:
        """
        特定の条件を満たすメールを待機
        
        Args:
            subject_contains: 件名に含まれる文字列
            from_contains: 送信元に含まれる文字列
            timeout: タイムアウト秒数
            interval: ポーリング間隔秒数
        
        Returns:
            マッチしたメッセージ、タイムアウト時はNone
        
        Raises:
            MailTMError: アカウント未作成時
        """
        if not self._account or not self._account.token:
            raise MailTMError("Not authenticated. Create account first.")
        
        start_time = time.time()
        checked_ids = set()
        
        while time.time() - start_time < timeout:
            messages = self.get_messages()
            
            for msg in messages:
                if msg.id in checked_ids:
                    continue
                
                checked_ids.add(msg.id)
                
                # 条件チェック
                match = True
                if subject_contains:
                    match = match and subject_contains.lower() in msg.subject.lower()
                if from_contains:
                    match = match and from_contains.lower() in msg.from_address.lower()
                
                if match:
                    # 詳細を取得して返す
                    return self.get_message(msg.id)
            
            time.sleep(interval)
        
        return None
    
    @staticmethod
    def _parse_datetime(dt_str: Optional[str]) -> Optional[datetime]:
        """ISO形式の日時文字列をパース"""
        if not dt_str:
            return None
        
        try:
            # ISO 8601 format
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except:
            return None


def create_temp_email() -> MailAccount:
    """
    一時メールアドレスを即座に作成
    
    Returns:
        作成されたアカウント情報
    
    Example:
        >>> account = create_temp_email()
        >>> print(account.address)
        'abc123xyz@mail.tm'
    """
    service = MailTMService()
    return service.create_account()


def quick_receive(timeout: int = 60) -> Optional[EmailMessage]:
    """
    一時メールを作成してメール受信を待機
    
    Args:
        timeout: 受信待機秒数
    
    Returns:
        受信したメッセージ、タイムアウト時はNone
    
    Example:
        >>> msg = quick_receive(timeout=120)
        >>> if msg:
        ...     print(f"From: {msg.from_address}")
        ...     print(f"Subject: {msg.subject}")
    """
    service = MailTMService()
    account = service.create_account()
    
    messages = service.poll_for_messages(timeout=timeout, max_messages=1)
    
    if messages:
        return messages[0]
    
    return None


if __name__ == "__main__":
    # テスト実行
    import json
    
    print("=== mail.tm Service Test ===")
    
    # アカウント作成
    service = MailTMService()
    account = service.create_account()
    
    print(f"Created account: {account.address}")
    print(f"Password: {account.password}")
    print(f"Token: {account.token[:20]}...")
    
    # メール受信ポーリング
    print("\nWaiting for messages (30s)...")
    messages = service.poll_for_messages(timeout=30, interval=5)
    
    if messages:
        print(f"Received {len(messages)} message(s)")
        for msg in messages:
            print(f"  - From: {msg.from_address}")
            print(f"    Subject: {msg.subject}")
    else:
        print("No messages received")
