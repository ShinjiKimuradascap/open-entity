#!/usr/bin/env python3
"""
全クラウドサービス自動登録スクリプト

PythonAnywhere, Render, Railwayに一括で自動登録します。
各サービスは順次実行され、認証情報がJSONファイルに保存されます。

使用方法:
    # 全サービスに登録
    python scripts/auto_register_all.py
    
    # 特定のサービスのみ
    python scripts/auto_register_all.py --services pythonanywhere,render
    
    # 既存アカウントをスキップ
    python scripts/auto_register_all.py --skip-existing

必要な環境変数:
    - MAIL_TM_TOKEN: mail.tm APIトークン（必須）
    - PA_PASSWORD: PythonAnywhereパスワード（省略時はデフォルト）
    - RENDER_PASSWORD: Renderパスワード（省略時はデフォルト）
    - RAILWAY_PASSWORD: Railwayパスワード（省略時はデフォルト）
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

# 個別登録スクリプトをインポート
sys.path.insert(0, str(Path(__file__).parent))

from auto_register_utils import (
    MailTMClient,
    RegistrationResult,
    save_credentials,
    list_saved_credentials,
    mask_sensitive_info
)

# 設定
AVAILABLE_SERVICES = ["pythonanywhere", "render", "railway"]
DEFAULT_PASSWORD = "Entity2026Secure!"
EMAIL_ADDRESS = "openentity908200@virgilian.com"


class BatchRegistration:
    """一括登録クラス"""
    
    def __init__(self, services: List[str], skip_existing: bool = False):
        self.services = services
        self.skip_existing = skip_existing
        self.results: List[RegistrationResult] = []
        self.mail_client: Optional[MailTMClient] = None
    
    def check_existing_account(self, service: str) -> bool:
        """既存アカウントが存在するかチェック"""
        creds = list_saved_credentials()
        for cred in creds:
            if cred.get("service") == service:
                print(f"[{service}] 既存アカウントが見つかりました: {cred.get('username') or cred.get('email')}")
                return True
        return False
    
    async def register_pythonanywhere(self) -> RegistrationResult:
        """PythonAnywhereに登録"""
        service = "pythonanywhere"
        print(f"\n{'='*60}")
        print(f"PythonAnywhere登録開始")
        print(f"{'='*60}")
        
        # 既存チェック
        if self.skip_existing and self.check_existing_account(service):
            return RegistrationResult(
                success=True,
                service=service,
                error_message="既存アカウントをスキップ"
            )
        
        try:
            # サブプロセスで実行
            import subprocess
            
            env = os.environ.copy()
            result = subprocess.run(
                [sys.executable, "scripts/auto_register_pythonanywhere.py"],
                capture_output=True,
                text=True,
                env=env,
                timeout=600  # 10分タイムアウト
            )
            
            success = result.returncode == 0
            
            # 出力から情報を抽出
            output = result.stdout + result.stderr
            username = None
            for line in output.split('\n'):
                if 'ユーザー名:' in line:
                    username = line.split(':')[-1].strip()
                elif 'Username:' in line:
                    username = line.split(':')[-1].strip()
            
            return RegistrationResult(
                success=success,
                service=service,
                username=username,
                email=EMAIL_ADDRESS,
                password=os.getenv("PA_PASSWORD", DEFAULT_PASSWORD),
                error_message=result.stderr if not success else None
            )
            
        except Exception as e:
            return RegistrationResult(
                success=False,
                service=service,
                error_message=str(e)
            )
    
    async def register_render(self) -> RegistrationResult:
        """Renderに登録"""
        service = "render"
        print(f"\n{'='*60}")
        print(f"Render登録開始")
        print(f"{'='*60}")
        
        if self.skip_existing and self.check_existing_account(service):
            return RegistrationResult(
                success=True,
                service=service,
                error_message="既存アカウントをスキップ"
            )
        
        try:
            import subprocess
            
            env = os.environ.copy()
            result = subprocess.run(
                [sys.executable, "scripts/auto_register_render.py"],
                capture_output=True,
                text=True,
                env=env,
                timeout=600
            )
            
            success = result.returncode == 0
            
            return RegistrationResult(
                success=success,
                service=service,
                email=EMAIL_ADDRESS,
                password=os.getenv("RENDER_PASSWORD", DEFAULT_PASSWORD),
                error_message=result.stderr if not success else None
            )
            
        except Exception as e:
            return RegistrationResult(
                success=False,
                service=service,
                error_message=str(e)
            )
    
    async def register_railway(self) -> RegistrationResult:
        """Railwayに登録"""
        service = "railway"
        print(f"\n{'='*60}")
        print(f"Railway登録開始")
        print(f"{'='*60}")
        
        if self.skip_existing and self.check_existing_account(service):
            return RegistrationResult(
                success=True,
                service=service,
                error_message="既存アカウントをスキップ"
            )
        
        try:
            import subprocess
            
            env = os.environ.copy()
            result = subprocess.run(
                [sys.executable, "scripts/auto_register_railway.py"],
                capture_output=True,
                text=True,
                env=env,
                timeout=600
            )
            
            success = result.returncode == 0
            
            # ユーザー名を抽出
            output = result.stdout + result.stderr
            username = None
            for line in output.split('\n'):
                if 'ユーザー名:' in line:
                    username = line.split(':')[-1].strip()
                elif 'Username:' in line:
                    username = line.split(':')[-1].strip()
            
            return RegistrationResult(
                success=success,
                service=service,
                username=username,
                email=EMAIL_ADDRESS,
                password=os.getenv("RAILWAY_PASSWORD", DEFAULT_PASSWORD),
                error_message=result.stderr if not success else None
            )
            
        except Exception as e:
            return RegistrationResult(
                success=False,
                service=service,
                error_message=str(e)
            )
    
    async def run(self) -> List[RegistrationResult]:
        """全サービスの登録を実行"""
        print("=" * 60)
        print("全クラウドサービス自動登録")
        print("=" * 60)
        print(f"対象サービス: {', '.join(self.services)}")
        print(f"メールアドレス: {EMAIL_ADDRESS}")
        
        # 環境変数チェック
        mail_token = os.getenv("MAIL_TM_TOKEN")
        if not mail_token:
            print("[Error] MAIL_TM_TOKEN環境変数が設定されていません")
            return []
        
        self.mail_client = MailTMClient(mail_token)
        
        # 各サービスを登録
        for service in self.services:
            if service == "pythonanywhere":
                result = await self.register_pythonanywhere()
            elif service == "render":
                result = await self.register_render()
            elif service == "railway":
                result = await self.register_railway()
            else:
                result = RegistrationResult(
                    success=False,
                    service=service,
                    error_message=f"未知のサービス: {service}"
                )
            
            self.results.append(result)
            
            # サービス間の待機
            if service != self.services[-1]:
                print("\n[Batch] 次のサービスまで10秒待機...")
                await asyncio.sleep(10)
        
        return self.results
    
    def generate_report(self) -> Path:
        """登録結果レポートを生成"""
        report = {
            "timestamp": datetime.now().isoformat(),
            "total_services": len(self.services),
            "successful": sum(1 for r in self.results if r.success),
            "failed": sum(1 for r in self.results if not r.success),
            "results": [r.to_dict() for r in self.results]
        }
        
        output_dir = Path("/home/moco/workspace/data/credentials")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        report_file = output_dir / f"registration_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        return report_file
    
    def print_summary(self):
        """サマリーを表示"""
        print("\n" + "=" * 60)
        print("登録結果サマリー")
        print("=" * 60)
        
        for result in self.results:
            status = "✅ 成功" if result.success else "❌ 失敗"
            print(f"\n[{result.service}] {status}")
            
            if result.username:
                print(f"  ユーザー名: {result.username}")
            if result.email:
                print(f"  メール: {result.email}")
            if result.password:
                print(f"  パスワード: {mask_sensitive_info(result.password)}")
            if result.error_message:
                print(f"  エラー: {result.error_message}")
        
        successful = sum(1 for r in self.results if r.success)
        print(f"\n{'='*60}")
        print(f"完了: {successful}/{len(self.results)} サービス")
        print("=" * 60)


def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(
        description="全クラウドサービス自動登録",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  # 全サービスに登録
  python scripts/auto_register_all.py
  
  # 特定のサービスのみ
  python scripts/auto_register_all.py --services pythonanywhere,render
  
  # 既存アカウントをスキップ
  python scripts/auto_register_all.py --skip-existing
        """
    )
    
    parser.add_argument(
        "--services",
        type=str,
        default=",".join(AVAILABLE_SERVICES),
        help=f"登録するサービス（カンマ区切り）\nデフォルト: {','.join(AVAILABLE_SERVICES)}"
    )
    
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="既存アカウントが存在する場合はスキップ"
    )
    
    parser.add_argument(
        "--list-existing",
        action="store_true",
        help="既存アカウントを一覧表示して終了"
    )
    
    args = parser.parse_args()
    
    # 既存アカウント一覧
    if args.list_existing:
        print("=" * 60)
        print("保存済みアカウント一覧")
        print("=" * 60)
        
        creds = list_saved_credentials()
        if not creds:
            print("保存済みアカウントはありません")
            return
        
        for cred in creds:
            service = cred.get("service", "unknown")
            identifier = cred.get("username") or cred.get("email", "unknown")
            created = cred.get("created_at", "unknown")
            print(f"  [{service}] {identifier} (作成: {created})")
        
        print(f"\n合計: {len(creds)}件")
        return
    
    # サービスリストをパース
    services = [s.strip().lower() for s in args.services.split(",")]
    
    # 無効なサービスをチェック
    invalid = [s for s in services if s not in AVAILABLE_SERVICES]
    if invalid:
        print(f"[Error] 無効なサービス: {', '.join(invalid)}")
        print(f"利用可能: {', '.join(AVAILABLE_SERVICES)}")
        sys.exit(1)
    
    # 一括登録を実行
    batch = BatchRegistration(services, args.skip_existing)
    
    try:
        asyncio.run(batch.run())
        batch.print_summary()
        
        # レポートを保存
        report_file = batch.generate_report()
        print(f"\nレポート保存: {report_file}")
        
        # 終了コード
        failed = sum(1 for r in batch.results if not r.success)
        if failed > 0:
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n[Interrupted] ユーザーにより中断されました")
        sys.exit(130)
    except Exception as e:
        print(f"\n[Error] 予期しないエラー: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
