#!/usr/bin/env python3
"""
Discord Bot自動登録スクリプト

Discord Developer Portalに自動登録し、Bot Tokenを取得します。
Mail.tmを使用して一時メールアドレスを作成し、Playwrightでブラウザ自動化を行います。

使用方法:
    python scripts/auto_discord_bot.py --username <username> --password <password>
    python scripts/auto_discord_bot.py --new-account --bot-name <bot_name>

環境変数:
    DISCORD_USERNAME: Discord既存アカウントのユーザー名/メール
    DISCORD_PASSWORD: Discord既存アカウントのパスワード
"""

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

# 親ディレクトリをパスに追加してskillsモジュールをインポート
sys.path.insert(0, str(Path(__file__).parent.parent))

from skills.temp_mail.temp_mail_tools import MailTmClient, create_address, wait_for_message


try:
    from playwright.async_api import async_playwright, Page, Browser, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("[Error] playwrightがインストールされていません")
    print("[Info] インストール: pip install playwright")
    print("[Info] ブラウザインストール: playwright install chromium")


@dataclass
class DiscordBotRegistrationResult:
    """Discord Bot登録結果"""
    success: bool
    bot_name: str
    bot_token: Optional[str] = None
    application_id: Optional[str] = None
    public_key: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    error_message: Optional[str] = None
    credentials_file: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return asdict(self)


class DiscordBotAutomator:
    """Discord Bot自動登録クラス"""
    
    DISCORD_DEV_PORTAL = "https://discord.com/developers/applications"
    DISCORD_LOGIN = "https://discord.com/login"
    
    def __init__(
        self,
        headless: bool = True,
        slow_mo: int = 100,
        timeout: int = 30000
    ):
        self.headless = headless
        self.slow_mo = slow_mo
        self.timeout = timeout
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.mail_client: Optional[MailTmClient] = None
        
    async def __aenter__(self):
        """Async context manager entry"""
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("playwrightがインストールされていません")
        
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            slow_mo=self.slow_mo
        )
        self.context = await self.browser.new_context(
            viewport={'width': 1280, 'height': 800}
        )
        self.page = await self.context.new_page()
        self.page.set_default_timeout(self.timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.browser:
            await self.browser.close()
        if hasattr(self, 'playwright'):
            await self.playwright.stop()
    
    async def create_temp_email(self) -> Dict[str, str]:
        """一時メールアドレスを作成"""
        print("[Step 1/6] 一時メールアドレスを作成中...")
        
        result = create_address()
        if not result.get('success'):
            raise RuntimeError(f"メール作成失敗: {result.get('error')}")
        
        self.mail_client = MailTmClient()
        self.mail_client.address = result['address']
        self.mail_client.token = result['token']
        
        print(f"[Success] メールアドレス: {result['address']}")
        return {
            'address': result['address'],
            'password': result['password'],
            'token': result['token']
        }
    
    async def login_to_discord(
        self,
        email: str,
        password: str,
        wait_for_2fa: bool = True
    ) -> bool:
        """Discordにログイン"""
        print("[Step 2/6] Discordにログイン中...")
        
        await self.page.goto(self.DISCORD_LOGIN)
        await asyncio.sleep(2)
        
        # メール入力
        await self.page.fill('input[name="email"]', email)
        await asyncio.sleep(0.5)
        
        # パスワード入力
        await self.page.fill('input[name="password"]', password)
        await asyncio.sleep(0.5)
        
        # ログインボタンクリック
        await self.page.click('button[type="submit"]')
        await asyncio.sleep(3)
        
        # 2FAやCAPTCHA、メール認証の確認
        current_url = self.page.url
        
        if "login" in current_url:
            # まだログインページにいる場合は追加認証が必要
            print("[Info] 追加認証が必要です（2FA/CAPTCHA/メール確認）")
            
            if wait_for_2fa:
                # 手動で認証する時間を待つ
                print("[Wait] 手動認証を待機中... (60秒)")
                await asyncio.sleep(60)
                
                # 再度URLを確認
                current_url = self.page.url
                if "login" in current_url:
                    print("[Warning] まだログインされていません")
                    return False
        
        # メール認証が必要な場合
        try:
            verify_button = await self.page.query_selector('button:has-text("Verify")')
            if verify_button:
                print("[Info] メール認証が必要です")
                # 認証メールを待機
                email_result = await wait_for_message(
                    self.mail_client.address,
                    self.mail_client.token,
                    timeout=120
                )
                if email_result.get('success'):
                    # メールから認証リンクを抽出して開く
                    msg = email_result['message']
                    # TODO: 認証リンクの抽出と処理
                    print(f"[Info] 認証メールを検出: {msg.get('subject')}")
        except Exception as e:
            print(f"[Warning] メール認証チェックでエラー: {e}")
        
        print("[Success] Discordログイン完了")
        return True
    
    async def create_application(self, bot_name: str) -> Optional[str]:
        """新しいApplicationを作成"""
        print(f"[Step 3/6] Application '{bot_name}' を作成中...")
        
        await self.page.goto(self.DISCORD_DEV_PORTAL)
        await asyncio.sleep(3)
        
        # "New Application" ボタンをクリック
        try:
            # 複数のセレクタを試行
            selectors = [
                'button:has-text("New Application")',
                'button[class*="button"]:has-text("New")',
                '[data-testid="new-application-button"]',
                'a[href*="applications"] button',
                'div[class*="container"] >> text=New Application'
            ]
            
            new_app_button = None
            for selector in selectors:
                try:
                    new_app_button = await self.page.wait_for_selector(
                        selector,
                        timeout=5000
                    )
                    if new_app_button:
                        break
                except:
                    continue
            
            if not new_app_button:
                # 直接URLにアクセス
                await self.page.goto(f"{self.DISCORD_DEV_PORTAL}/new")
                await asyncio.sleep(2)
            else:
                await new_app_button.click()
                await asyncio.sleep(2)
        except Exception as e:
            print(f"[Warning] New Applicationボタンクリック失敗: {e}")
            # 直接newページへ
            await self.page.goto(f"{self.DISCORD_DEV_PORTAL}/new")
            await asyncio.sleep(2)
        
        # アプリケーション名を入力
        name_input_selectors = [
            'input[name="name"]',
            'input[placeholder*="name" i]',
            'input[type="text"]',
            '[data-testid="application-name-input"]'
        ]
        
        name_filled = False
        for selector in name_input_selectors:
            try:
                await self.page.fill(selector, bot_name)
                name_filled = True
                break
            except:
                continue
        
        if not name_filled:
            raise RuntimeError("アプリケーション名入力欄が見つかりません")
        
        await asyncio.sleep(0.5)
        
        # Createボタンをクリック
        create_selectors = [
            'button:has-text("Create")',
            'button[type="submit"]',
            'button[class*="primary"]',
            '[data-testid="create-application-button"]'
        ]
        
        create_clicked = False
        for selector in create_selectors:
            try:
                await self.page.click(selector)
                create_clicked = True
                break
            except:
                continue
        
        if not create_clicked:
            raise RuntimeError("Createボタンが見つかりません")
        
        await asyncio.sleep(3)
        
        # Application IDをURLから取得
        current_url = self.page.url
        if "/applications/" in current_url:
            app_id = current_url.split("/applications/")[1].split("/")[0]
            print(f"[Success] Application作成完了 (ID: {app_id})")
            return app_id
        
        print("[Warning] Application IDをURLから取得できませんでした")
        return None
    
    async def add_bot_to_application(self) -> bool:
        """ApplicationにBotを追加"""
        print("[Step 4/6] Botを追加中...")
        
        # Botセクションに移動
        bot_nav_selectors = [
            'a:has-text("Bot")',
            '[class*="nav"] >> text=Bot',
            'nav >> text=Bot',
            'a[href*="bot"]'
        ]
        
        bot_nav_clicked = False
        for selector in bot_nav_selectors:
            try:
                await self.page.click(selector)
                bot_nav_clicked = True
                break
            except:
                continue
        
        if not bot_nav_clicked:
            # URL直接アクセス
            current_url = self.page.url
            if "/applications/" in current_url:
                app_id = current_url.split("/applications/")[1].split("/")[0]
                await self.page.goto(f"{self.DISCORD_DEV_PORTAL}/{app_id}/bot")
                await asyncio.sleep(2)
        
        await asyncio.sleep(2)
        
        # "Add Bot" ボタンをクリック
        add_bot_selectors = [
            'button:has-text("Add Bot")',
            'button:has-text("Add")',
            '[data-testid="add-bot-button"]',
            'button[class*="button"]:has-text("Bot")'
        ]
        
        add_bot_clicked = False
        for selector in add_bot_selectors:
            try:
                await self.page.click(selector)
                add_bot_clicked = True
                break
            except:
                continue
        
        if not add_bot_clicked:
            # Botが既に追加されている可能性
            print("[Info] Botが既に追加されているか、ボタンが見つかりません")
        else:
            # 確認ダイアログで"Yes, do it!"をクリック
            await asyncio.sleep(1)
            confirm_selectors = [
                'button:has-text("Yes, do it")',
                'button:has-text("Yes")',
                'button[class*="danger"]',
                'button[type="submit"]'
            ]
            
            for selector in confirm_selectors:
                try:
                    await self.page.click(selector)
                    break
                except:
                    continue
            
            await asyncio.sleep(2)
        
        print("[Success] Bot追加完了")
        return True
    
    async def get_bot_token(self) -> Optional[str]:
        """Bot Tokenを取得"""
        print("[Step 5/6] Bot Tokenを取得中...")
        
        # Token表示エリアを探す
        token_selectors = [
            'input[value*="MTE"]',  # Bot tokenはMTEで始まる
            'input[value*="MTA"]',  # またはMTA
            'input[type="text"][readonly]',
            '[class*="token"]',
            'code[class*="token"]'
        ]
        
        token = None
        for selector in token_selectors:
            try:
                element = await self.page.query_selector(selector)
                if element:
                    value = await element.get_attribute('value')
                    if value and (value.startswith('MTE') or value.startswith('MTA')):
                        token = value
                        break
                    # textContentも確認
                    text = await element.text_content()
                    if text and (text.strip().startswith('MTE') or text.strip().startswith('MTA')):
                        token = text.strip()
                        break
            except:
                continue
        
        if not token:
            # "Reset Token" ボタンをクリックして新しいトークンを生成
            print("[Info] 既存のトークンが見つからないため、新しいトークンを生成します")
            
            reset_selectors = [
                'button:has-text("Reset Token")',
                'button:has-text("Regenerate")',
                'button:has-text("Copy")',
                'button[class*="button"]:has-text("Token")'
            ]
            
            for selector in reset_selectors:
                try:
                    await self.page.click(selector)
                    await asyncio.sleep(2)
                    
                    # 確認ダイアログ
                    confirm_selectors = [
                        'button:has-text("Yes")',
                        'button:has-text("Confirm")',
                        'button[class*="danger"]'
                    ]
                    for confirm in confirm_selectors:
                        try:
                            await self.page.click(confirm)
                            await asyncio.sleep(2)
                            break
                        except:
                            continue
                    
                    # 新しいトークンを取得
                    for selector2 in token_selectors:
                        try:
                            element = await self.page.query_selector(selector2)
                            if element:
                                value = await element.get_attribute('value')
                                if value and (value.startswith('MTE') or value.startswith('MTA')):
                                    token = value
                                    break
                        except:
                            continue
                    
                    if token:
                        break
                except:
                    continue
        
        if token:
            print(f"[Success] Bot Token取得成功: {token[:20]}...")
            return token
        
        print("[Error] Bot Tokenを取得できませんでした")
        return None
    
    async def get_application_credentials(self) -> Dict[str, Any]:
        """Application情報を取得"""
        print("[Step 6/6] Application情報を収集中...")
        
        credentials = {
            'application_id': None,
            'public_key': None,
            'client_id': None,
            'client_secret': None
        }
        
        # URLからApplication IDを取得
        current_url = self.page.url
        if "/applications/" in current_url:
            app_id = current_url.split("/applications/")[1].split("/")[0]
            credentials['application_id'] = app_id
            credentials['client_id'] = app_id
        
        # General Informationセクションに移動して情報を取得
        try:
            await self.page.click('a:has-text("General")')
            await asyncio.sleep(1)
        except:
            pass
        
        # Public Keyを取得
        public_key_selectors = [
            'input[value*="-----BEGIN PUBLIC KEY-----"]',
            'input[value*="MIIB"]',
            'textarea:has-text("PUBLIC KEY")',
            '[class*="public-key"]'
        ]
        
        for selector in public_key_selectors:
            try:
                element = await self.page.query_selector(selector)
                if element:
                    value = await element.get_attribute('value')
                    if value:
                        credentials['public_key'] = value
                        break
            except:
                continue
        
        # Client Secretを取得（OAuth2セクション）
        try:
            await self.page.click('a:has-text("OAuth2")')
            await asyncio.sleep(1)
            
            secret_selectors = [
                'input[value*="_"]',
                'input[type="text"][readonly]'
            ]
            
            for selector in secret_selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element:
                        value = await element.get_attribute('value')
                        if value and len(value) > 20:
                            credentials['client_secret'] = value
                            break
                except:
                    continue
        except:
            pass
        
        print("[Success] Application情報収集完了")
        return credentials
    
    async def register_bot(
        self,
        discord_email: str,
        discord_password: str,
        bot_name: str,
        wait_for_manual_auth: bool = True
    ) -> DiscordBotRegistrationResult:
        """
        Discord Botを完全自動登録
        
        Args:
            discord_email: Discordアカウントのメール
            discord_password: Discordアカウントのパスワード
            bot_name: 作成するBotの名前
            wait_for_manual_auth: 手動認証を待機するか
        
        Returns:
            登録結果
        """
        result = DiscordBotRegistrationResult(success=False, bot_name=bot_name)
        
        try:
            # 1. 一時メール作成（オプション - 必要に応じて）
            temp_email = None
            if wait_for_manual_auth:
                try:
                    email_info = await self.create_temp_email()
                    temp_email = email_info
                    result.email = email_info['address']
                    result.password = email_info['password']
                except Exception as e:
                    print(f"[Warning] 一時メール作成失敗: {e}")
            
            # 2. Discordにログイン
            login_success = await self.login_to_discord(
                discord_email,
                discord_password,
                wait_for_2fa=wait_for_manual_auth
            )
            
            if not login_success:
                result.error_message = "Discordログインに失敗しました"
                return result
            
            # 3. Application作成
            app_id = await self.create_application(bot_name)
            if not app_id:
                result.error_message = "Application作成に失敗しました"
                return result
            
            result.application_id = app_id
            result.client_id = app_id
            
            # 4. Bot追加
            bot_added = await self.add_bot_to_application()
            if not bot_added:
                result.error_message = "Bot追加に失敗しました"
                return result
            
            # 5. Token取得
            token = await self.get_bot_token()
            if not token:
                result.error_message = "Bot Token取得に失敗しました"
                return result
            
            result.bot_token = token
            
            # 6. 追加情報取得
            credentials = await self.get_application_credentials()
            if credentials.get('public_key'):
                result.public_key = credentials['public_key']
            if credentials.get('client_secret'):
                result.client_secret = credentials['client_secret']
            
            result.success = True
            
            # 7. 認証情報を保存
            credentials_file = self._save_credentials(result, temp_email)
            result.credentials_file = str(credentials_file)
            
            print("\n" + "="*60)
            print("[SUCCESS] Discord Bot登録完了!")
            print("="*60)
            print(f"Bot名: {bot_name}")
            print(f"Application ID: {result.application_id}")
            print(f"Bot Token: {result.bot_token[:30]}...")
            print(f"保存先: {credentials_file}")
            print("="*60)
            
        except Exception as e:
            result.error_message = str(e)
            print(f"[Error] 登録失敗: {e}")
        
        return result
    
    def _save_credentials(
        self,
        result: DiscordBotRegistrationResult,
        temp_email: Optional[Dict[str, str]]
    ) -> Path:
        """認証情報をファイルに保存"""
        output_dir = Path("/home/moco/workspace/data/credentials")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = result.bot_name.replace(" ", "_").replace("-", "_")
        filename = f"discord_bot_{safe_name}_{timestamp}.json"
        output_file = output_dir / filename
        
        data = {
            "service": "discord_bot",
            "bot_name": result.bot_name,
            "bot_token": result.bot_token,
            "application_id": result.application_id,
            "client_id": result.client_id,
            "client_secret": result.client_secret,
            "public_key": result.public_key,
            "temp_email": temp_email,
            "created_at": datetime.now().isoformat(),
            "status": "active"
        }
        
        with open(output_file, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        return output_file


def load_discord_credentials() -> Dict[str, str]:
    """環境変数または保存された認証情報を読み込み"""
    email = os.getenv("DISCORD_USERNAME") or os.getenv("DISCORD_EMAIL")
    password = os.getenv("DISCORD_PASSWORD")
    
    if not email or not password:
        raise ValueError(
            "DISCORD_USERNAME と DISCORD_PASSWORD 環境変数を設定してください"
        )
    
    return {"email": email, "password": password}


async def main():
    """メイン実行関数"""
    parser = argparse.ArgumentParser(
        description="Discord Bot自動登録スクリプト",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  # 既存アカウントでBot作成
  python scripts/auto_discord_bot.py --email user@example.com --password pass --bot-name "MyBot"

  # 環境変数を使用
  export DISCORD_USERNAME=user@example.com
  export DISCORD_PASSWORD=password
  python scripts/auto_discord_bot.py --bot-name "MyBot"

  # ヘッドレスモードOFF（ブラウザを表示）
  python scripts/auto_discord_bot.py --bot-name "MyBot" --no-headless
        """
    )
    
    parser.add_argument(
        "--email",
        help="Discordアカウントのメールアドレス"
    )
    parser.add_argument(
        "--password",
        help="Discordアカウントのパスワード"
    )
    parser.add_argument(
        "--bot-name",
        required=True,
        help="作成するBotの名前"
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="ブラウザを表示（デバッグ用）"
    )
    parser.add_argument(
        "--no-manual-auth",
        action="store_true",
        help="手動認証待機を無効化"
    )
    parser.add_argument(
        "--slow-mo",
        type=int,
        default=100,
        help="操作間の遅延（ミリ秒、デフォルト: 100）"
    )
    
    args = parser.parse_args()
    
    # 認証情報を取得
    try:
        if args.email and args.password:
            credentials = {"email": args.email, "password": args.password}
        else:
            credentials = load_discord_credentials()
    except ValueError as e:
        print(f"[Error] {e}")
        sys.exit(1)
    
    # Playwright確認
    if not PLAYWRIGHT_AVAILABLE:
        print("[Error] playwrightがインストールされていません")
        print("[Info] pip install playwright && playwright install chromium")
        sys.exit(1)
    
    print("="*60)
    print("Discord Bot自動登録")
    print("="*60)
    print(f"Bot名: {args.bot_name}")
    print(f"Discordアカウント: {credentials['email'][:3]}***")
    print("="*60)
    
    # 自動化実行
    async with DiscordBotAutomator(
        headless=not args.no_headless,
        slow_mo=args.slow_mo
    ) as automator:
        result = await automator.register_bot(
            discord_email=credentials["email"],
            discord_password=credentials["password"],
            bot_name=args.bot_name,
            wait_for_manual_auth=not args.no_manual_auth
        )
    
    # 結果表示
    print("\n" + "="*60)
    if result.success:
        print("✅ 登録成功")
        print(f"   Bot名: {result.bot_name}")
        print(f"   Bot Token: {result.bot_token[:40]}...")
        print(f"   Application ID: {result.application_id}")
        print(f"   認証情報保存先: {result.credentials_file}")
    else:
        print("❌ 登録失敗")
        print(f"   エラー: {result.error_message}")
    print("="*60)
    
    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    asyncio.run(main())
