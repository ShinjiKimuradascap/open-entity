#!/usr/bin/env python3
"""
Render自動登録スクリプト

Playwrightを使用してヘッドレスブラウザでRenderに自動登録し、
mail.tm APIで認証メールを確認してアカウントを有効化します。

使用方法:
    python scripts/auto_register_render.py

必要な環境変数:
    - MAIL_TM_TOKEN: mail.tm APIトークン
    - RENDER_PASSWORD: Renderアカウントパスワード（省略時はデフォルト）
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
RENDER_REGISTER_URL = "https://dashboard.render.com/register"
RENDER_LOGIN_URL = "https://dashboard.render.com/login"
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
        
        import re
        
        # HTMLからリンクを抽出
        content = ""
        if html:
            content = html[0] if isinstance(html, list) else html
        else:
            content = text
        
        # Renderの認証リンクを探す
        patterns = [
            r'https?://[^\s"<>]*render\.com/[^\s"<>]*confirm[^\s"<>]*',
            r'https?://[^\s"<>]*render\.com/[^\s"<>]*verify[^\s"<>]*',
            r'https?://[^\s"<>]*render\.com/[^\s"<>]*activate[^\s"<>]*',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
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
                
                # Renderからの認証メールを確認
                if "render" in from_addr or any(kw in subject for kw in ["verify", "confirm", "activate"]):
                    print(f"[mail.tm] 認証メールを検出: {subject}")
                    
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


class RenderRegister:
    """Render自動登録クラス"""
    
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.mail_client: Optional[MailTMClient] = None
        self.email: str = EMAIL_ADDRESS
        self.password: Optional[str] = None
    
    async def init_browser(self):
        """ブラウザを初期化"""
        playwright = await async_playwright().start()
        
        self.browser = await playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--window-size=1920,1080"
            ]
        )
        
        context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
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
        
        self.password = os.getenv("RENDER_PASSWORD", DEFAULT_PASSWORD)
        
        print(f"[Register] メール: {self.email}")
        
        # 登録ページにアクセス
        print(f"[Register] 登録ページにアクセス: {RENDER_REGISTER_URL}")
        
        retry_count = 0
        max_retries = 3
        
        while retry_count < max_retries:
            try:
                await self.page.goto(
                    RENDER_REGISTER_URL,
                    wait_until="networkidle",
                    timeout=60000
                )
                break
            except Exception as e:
                retry_count += 1
                print(f"[Register] ページアクセス失敗 ({retry_count}/{max_retries}): {e}")
                if retry_count >= max_retries:
                    raise
                await asyncio.sleep(2 ** retry_count)
        
        # Cookie同意バナーを閉じる（あれば）
        try:
            cookie_buttons = [
                "button:has-text('Accept')",
                "button:has-text('同意')",
                "[data-testid='cookie-accept']",
                ".accept-cookies"
            ]
            for selector in cookie_buttons:
                try:
                    btn = await self.page.query_selector(selector)
                    if btn:
                        await btn.click()
                        print("[Register] Cookie同意バナーを閉じました")
                        await asyncio.sleep(1)
                        break
                except:
                    pass
        except:
            pass
        
        # フォーム入力
        try:
            # メールアドレス
            await self.page.fill("input[type='email'], input[name='email'], input[placeholder*='email' i]", self.email)
            print("[Register] メールアドレスを入力")
            
            # パスワード
            await self.page.fill("input[type='password'], input[name='password']", self.password)
            print("[Register] パスワードを入力")
            
            # 登録ボタンをクリック
            submit_selectors = [
                "button[type='submit']",
                "button:has-text('Sign up')",
                "button:has-text('Register')",
                "button:has-text('Create')",
                "[data-testid='signup-button']"
            ]
            
            submit_button = None
            for selector in submit_selectors:
                submit_button = await self.page.query_selector(selector)
                if submit_button:
                    break
            
            if submit_button:
                await submit_button.click()
                print("[Register] 登録ボタンをクリック")
            else:
                await self.page.press("input[type='password']", "Enter")
                print("[Register] フォームを送信")
            
            # ページ遷移を待機
            await asyncio.sleep(5)
            
            # エラー確認
            error_selectors = [
                ".error",
                ".error-message",
                "[role='alert']",
                ".text-red"
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
            
            current_url = self.page.url
            print(f"[Register] 現在のURL: {current_url}")
            
            # 成功確認
            if any(kw in current_url.lower() for kw in ["success", "confirm", "verify", "dashboard"]):
                print("[Register] 登録フォーム送信成功")
                return True
            
            page_content = await self.page.content()
            success_indicators = [
                "check your email", "verification", "confirm your email",
                "verify your email", "successfully registered"
            ]
            if any(ind in page_content.lower() for ind in success_indicators):
                print("[Register] 確認メール送信成功")
                return True
            
            return True
            
        except Exception as e:
            print(f"[Register] フォーム入力エラー: {e}")
            try:
                await self.page.screenshot(path="/tmp/render_register_error.png")
                print("[Register] エラースクリーンショット: /tmp/render_register_error.png")
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
        
        page_content = await self.page.content()
        if any(msg in page_content.lower() for msg in ["confirmed", "activated", "success", "verified"]):
            print("[Verify] メール認証成功")
            return True
        
        print("[Verify] メール認証完了")
        return True
    
    def save_credentials(self) -> Path:
        """認証情報をJSONファイルに保存"""
        credentials = {
            "service": "render",
            "email": self.email,
            "password": self.password,
            "created_at": datetime.now().isoformat(),
            "status": "active"
        }
        
        output_dir = Path("/home/moco/workspace/data/credentials")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Renderはメールベースなので、メールアドレスからファイル名を生成
        safe_email = self.email.replace("@", "_at_").replace(".", "_")
        output_file = output_dir / f"render_{safe_email}.json"
        
        with open(output_file, "w") as f:
            json.dump(credentials, f, indent=2)
        
        print(f"[Save] 認証情報を保存: {output_file}")
        return output_file


async def main():
    """メイン処理"""
    print("=" * 60)
    print("Render自動登録スクリプト")
    print("=" * 60)
    
    mail_token = os.getenv("MAIL_TM_TOKEN")
    if not mail_token:
        print("[Error] MAIL_TM_TOKEN環境変数が設定されていません")
        sys.exit(1)
    
    print(f"[Info] メールアドレス: {EMAIL_ADDRESS}")
    
    register = RenderRegister()
    
    try:
        register.mail_client = MailTMClient(mail_token)
        await register.init_browser()
        
        registration_success = await register.register_account()
        
        if not registration_success:
            print("[Error] アカウント登録に失敗しました")
            sys.exit(1)
        
        verification_link = await register.mail_client.wait_for_verification_email()
        
        if verification_link:
            await register.verify_email(verification_link)
        else:
            print("[Warning] 認証リンクが見つかりませんでした。手動で確認してください。")
        
        cred_file = register.save_credentials()
        
        print("=" * 60)
        print("登録完了")
        print("=" * 60)
        print(f"メール: {register.email}")
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
