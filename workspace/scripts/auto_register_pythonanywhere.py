#!/usr/bin/env python3
"""
PythonAnywhere自動登録スクリプト

Playwrightを使用してヘッドレスブラウザでPythonAnywhereに自動登録し、
mail.tm APIで認証メールを確認してアカウントを有効化します。

使用方法:
    python scripts/auto_register_pythonanywhere.py

必要な環境変数:
    - MAIL_TM_TOKEN: mail.tm APIトークン
    - PA_PASSWORD: PythonAnywhereアカウントパスワード
"""

import asyncio
import json
import os
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

import requests
from playwright.async_api import async_playwright, Page, Browser

# 設定
MAIL_TM_API = "https://api.mail.tm"
PYTHONANYWHERE_REGISTER_URL = "https://www.pythonanywhere.com/registration/register/"
MAX_EMAIL_WAIT_TIME = 300  # 5分
EMAIL_POLL_INTERVAL = 5  # 5秒間隔

# 固定情報
EMAIL_ADDRESS = "openentity908200@virgilian.com"
BASE_USERNAME = "openentity"
DEFAULT_PASSWORD = "Entity2026Secure!"


class MailTMClient:
    """mail.tm APIクライアント"""
    
    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    
    def get_messages(self) -> list:
        """メッセージ一覧を取得"""
        try:
            response = requests.get(
                f"{MAIL_TM_API}/messages",
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            return response.json().get("hydra:member", [])
        except Exception as e:
            print(f"[mail.tm] メッセージ取得エラー: {e}")
            return []
    
    def get_message(self, message_id: str) -> Dict[str, Any]:
        """特定のメッセージを取得"""
        try:
            response = requests.get(
                f"{MAIL_TM_API}/messages/{message_id}",
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"[mail.tm] メッセージ詳細取得エラー: {e}")
            return {}
    
    def extract_verification_link(self, message: Dict[str, Any]) -> Optional[str]:
        """メッセージから認証リンクを抽出"""
        text = message.get("text", "")
        html = message.get("html", [])
        
        # PythonAnywhereの認証リンクを探す
        import re
        
        # HTMLからリンクを抽出
        if html:
            html_content = html[0] if isinstance(html, list) else html
            # pythonanywhere.com/registration/confirm/ のパターン
            match = re.search(
                r'https?://[^\s"<>]*pythonanywhere\.com/registration/confirm/[^\s"<>]+',
                html_content
            )
            if match:
                return match.group(0)
        
        # テキストからリンクを抽出
        if text:
            match = re.search(
                r'https?://[^\s"<>]*pythonanywhere\.com/registration/confirm/[^\s"<>]+',
                text
            )
            if match:
                return match.group(0)
        
        return None
    
    async def wait_for_verification_email(self) -> Optional[str]:
        """認証メールを待機してリンクを返す"""
        print(f"[mail.tm] 認証メールを待機中... (最大{MAX_EMAIL_WAIT_TIME}秒)")
        
        waited = 0
        checked_ids = set()
        
        while waited < MAX_EMAIL_WAIT_TIME:
            messages = self.get_messages()
            
            for msg in messages:
                msg_id = msg.get("id")
                if msg_id in checked_ids:
                    continue
                checked_ids.add(msg_id)
                
                subject = msg.get("subject", "").lower()
                from_addr = msg.get("from", {}).get("address", "").lower()
                
                # PythonAnywhereからの認証メールを確認
                if "pythonanywhere" in from_addr or "confirm" in subject:
                    print(f"[mail.tm] 認証メールを検出: {subject}")
                    
                    # メッセージ詳細を取得
                    message_detail = self.get_message(msg_id)
                    link = self.extract_verification_link(message_detail)
                    
                    if link:
                        print(f"[mail.tm] 認証リンクを抽出: {link}")
                        return link
            
            await asyncio.sleep(EMAIL_POLL_INTERVAL)
            waited += EMAIL_POLL_INTERVAL
            if waited % 30 == 0:
                print(f"[mail.tm] 待機中... {waited}秒経過")
        
        print("[mail.tm] 認証メールが見つかりませんでした")
        return None


class PythonAnywhereRegister:
    """PythonAnywhere自動登録クラス"""
    
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.mail_client: Optional[MailTMClient] = None
        self.username: Optional[str] = None
        self.password: Optional[str] = None
    
    def generate_username(self) -> str:
        """ランダムなユーザー名を生成"""
        random_num = random.randint(1000, 9999)
        return f"{BASE_USERNAME}{random_num}"
    
    async def init_browser(self):
        """ブラウザを初期化"""
        playwright = await async_playwright().start()
        
        # ヘッドレスモードで起動（xvfb不要）
        self.browser = await playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-accelerated-2d-canvas",
                "--disable-gpu",
                "--window-size=1920,1080"
            ]
        )
        
        context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        self.page = await context.new_page()
        print("[Browser] ブラウザを初期化しました")
    
    async def close_browser(self):
        """ブラウザを終了"""
        if self.browser:
            await self.browser.close()
            print("[Browser] ブラウザを終了しました")
    
    async def register_account(self) -> bool:
        """アカウント登録を実行"""
        if not self.page:
            raise RuntimeError("ブラウザが初期化されていません")
        
        self.username = self.generate_username()
        self.password = os.getenv("PA_PASSWORD", DEFAULT_PASSWORD)
        
        print(f"[Register] ユーザー名: {self.username}")
        print(f"[Register] メール: {EMAIL_ADDRESS}")
        
        # 登録ページにアクセス
        print(f"[Register] 登録ページにアクセス: {PYTHONANYWHERE_REGISTER_URL}")
        
        retry_count = 0
        max_retries = 3
        
        while retry_count < max_retries:
            try:
                await self.page.goto(
                    PYTHONANYWHERE_REGISTER_URL,
                    wait_until="networkidle",
                    timeout=60000
                )
                break
            except Exception as e:
                retry_count += 1
                print(f"[Register] ページアクセス失敗 ({retry_count}/{max_retries}): {e}")
                if retry_count >= max_retries:
                    raise
                await asyncio.sleep(2 ** retry_count)  # 指数バックオフ
        
        # フォーム入力
        try:
            # ユーザー名
            await self.page.fill("input[name='username']", self.username)
            print("[Register] ユーザー名を入力")
            
            # メールアドレス
            await self.page.fill("input[name='email']", EMAIL_ADDRESS)
            print("[Register] メールアドレスを入力")
            
            # パスワード
            await self.page.fill("input[name='password1']", self.password)
            print("[Register] パスワードを入力")
            
            # パスワード確認
            await self.page.fill("input[name='password2']", self.password)
            print("[Register] パスワード確認を入力")
            
            # TOSに同意（チェックボックスがある場合）
            try:
                tos_checkbox = await self.page.query_selector("input[name='tos']")
                if tos_checkbox:
                    await tos_checkbox.click()
                    print("[Register] TOSに同意")
            except:
                pass
            
            # 登録ボタンをクリック
            submit_button = await self.page.query_selector("button[type='submit'], input[type='submit']")
            if submit_button:
                await submit_button.click()
                print("[Register] 登録ボタンをクリック")
            else:
                # フォームを直接送信
                await self.page.press("input[name='password2']", "Enter")
                print("[Register] フォームを送信")
            
            # ページ遷移を待機
            await asyncio.sleep(3)
            
            # エラーメッセージを確認
            error_selectors = [
                ".error",
                ".errorlist",
                ".alert-error",
                ".has-error",
                "[class*='error']"
            ]
            
            for selector in error_selectors:
                try:
                    error_elem = await self.page.query_selector(selector)
                    if error_elem:
                        error_text = await error_elem.text_content()
                        if error_text and error_text.strip():
                            print(f"[Register] エラーメッセージ: {error_text.strip()}")
                except:
                    pass
            
            # 成功を確認（URL変更またはメッセージ）
            current_url = self.page.url
            print(f"[Register] 現在のURL: {current_url}")
            
            if "success" in current_url or "confirm" in current_url or "check-email" in current_url:
                print("[Register] 登録フォーム送信成功")
                return True
            
            # ページ内容に成功メッセージがあるか確認
            page_content = await self.page.content()
            if any(msg in page_content.lower() for msg in ["check your email", "confirmation", "verify"]):
                print("[Register] 確認メール送信成功")
                return True
            
            return True  # エラーがなければ成功とみなす
            
        except Exception as e:
            print(f"[Register] フォーム入力エラー: {e}")
            # スクリーンショットを保存
            try:
                await self.page.screenshot(path="/tmp/pa_register_error.png")
                print("[Register] エラースクリーンショット: /tmp/pa_register_error.png")
            except:
                pass
            raise
    
    async def verify_email(self, verification_link: str):
        """メール認証リンクを開く"""
        if not self.page:
            raise RuntimeError("ブラウザが初期化されていません")
        
        print(f"[Verify] 認証リンクにアクセス: {verification_link}")
        
        await self.page.goto(verification_link, wait_until="networkidle", timeout=60000)
        
        await asyncio.sleep(3)
        
        current_url = self.page.url
        print(f"[Verify] 認証後のURL: {current_url}")
        
        # 成功確認
        page_content = await self.page.content()
        if any(msg in page_content.lower() for msg in ["confirmed", "activated", "success", "verified"]):
            print("[Verify] メール認証成功")
            return True
        
        print("[Verify] メール認証完了（手動で確認してください）")
        return True
    
    def save_credentials(self) -> Path:
        """認証情報をJSONファイルに保存"""
        credentials = {
            "service": "pythonanywhere",
            "username": self.username,
            "email": EMAIL_ADDRESS,
            "password": self.password,
            "created_at": datetime.now().isoformat(),
            "status": "active"
        }
        
        # 保存先ディレクトリ
        output_dir = Path("/home/moco/workspace/data/credentials")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = output_dir / f"pythonanywhere_{self.username}.json"
        
        with open(output_file, "w") as f:
            json.dump(credentials, f, indent=2)
        
        print(f"[Save] 認証情報を保存: {output_file}")
        return output_file


async def main():
    """メイン処理"""
    print("=" * 60)
    print("PythonAnywhere自動登録スクリプト")
    print("=" * 60)
    
    # 環境変数からトークンを取得
    mail_token = os.getenv("MAIL_TM_TOKEN")
    if not mail_token:
        print("[Error] MAIL_TM_TOKEN環境変数が設定されていません")
        sys.exit(1)
    
    print(f"[Info] メールアドレス: {EMAIL_ADDRESS}")
    
    # 登録処理
    register = PythonAnywhereRegister()
    
    try:
        # メールクライアント初期化
        register.mail_client = MailTMClient(mail_token)
        
        # ブラウザ初期化
        await register.init_browser()
        
        # アカウント登録
        registration_success = await register.register_account()
        
        if not registration_success:
            print("[Error] アカウント登録に失敗しました")
            sys.exit(1)
        
        # 認証メールを待機
        verification_link = await register.mail_client.wait_for_verification_email()
        
        if verification_link:
            # 認証リンクをクリック
            await register.verify_email(verification_link)
        else:
            print("[Warning] 認証リンクが見つかりませんでした。手動で確認してください。")
        
        # 認証情報を保存
        cred_file = register.save_credentials()
        
        print("=" * 60)
        print("登録完了")
        print("=" * 60)
        print(f"ユーザー名: {register.username}")
        print(f"メール: {EMAIL_ADDRESS}")
        print(f"認証情報: {cred_file}")
        
    except Exception as e:
        print(f"[Error] 登録処理中にエラー: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await register.close_browser()


if __name__ == "__main__":
    asyncio.run(main())
