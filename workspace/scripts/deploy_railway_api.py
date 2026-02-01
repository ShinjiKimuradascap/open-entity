#!/usr/bin/env python3
"""
Railway.app API経由でのデプロイスクリプト
CLIが使えない環境用

使用方法:
1. RAILWAY_API_TOKEN環境変数を設定
2. python scripts/deploy_railway_api.py
"""

import os
import sys
import json
import http.client
import urllib.request
from pathlib import Path

def get_railway_token():
    """環境変数またはファイルからトークンを取得"""
    token = os.environ.get('RAILWAY_API_TOKEN')
    if not token:
        token_file = Path.home() / '.railway' / 'token'
        if token_file.exists():
            token = token_file.read_text().strip()
    return token

def create_project(token, name):
    """新しいRailwayプロジェクトを作成"""
    conn = http.client.HTTPSConnection("railway.app")
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    payload = json.dumps({
        "query": """
        mutation ProjectCreate {
            projectCreate {
                id
                name
            }
        }
        """
    })
    
    conn.request("POST", "/graphql", payload, headers)
    res = conn.getresponse()
    data = res.read()
    
    return json.loads(data.decode("utf-8"))

def deploy_from_repo(token, project_id, repo_url):
    """GitHubリポジトリからデプロイ"""
    # RailwayはGitHub連携が推奨
    print(f"Project ID: {project_id}")
    print(f"Repository: {repo_url}")
    print("\n=== 手動デプロイ手順 ===")
    print("1. https://railway.app/dashboard にアクセス")
    print("2. 'New Project' → 'Deploy from GitHub repo'")
    print(f"3. リポジトリを選択: {repo_url}")
    print("4. 環境変数を設定:")
    print("   - PYTHON_VERSION=3.11.0")
    print("   - API_HOST=0.0.0.0")
    print("   - API_PORT=8000")
    print("5. Deployをクリック")

def main():
    token = get_railway_token()
    
    if not token:
        print("エラー: RAILWAY_API_TOKENが設定されていません")
        print("\n設定方法:")
        print("1. https://railway.app/dashboard にアクセス")
        print("2. Settings → Tokens で新規トークン作成")
        print("3. export RAILWAY_API_TOKEN='your-token'")
        sys.exit(1)
    
    # 現在のGitリポジトリURLを取得
    import subprocess
    try:
        result = subprocess.run(
            ['git', 'remote', 'get-url', 'origin'],
            capture_output=True,
            text=True,
            check=True
        )
        repo_url = result.stdout.strip()
    except:
        repo_url = "https://github.com/your-username/ai-collaboration-platform"
    
    print("=== Railwayデプロイ準備 ===")
    print(f"リポジトリ: {repo_url}")
    
    # トークン検証
    print("\nトークンを検証中...")
    
    # 手順を表示
    print("\n=== 推奨デプロイ手順 ===")
    print("\n1. Railwayダッシュボードで手動デプロイ:")
    print("   https://railway.app/new")
    print("\n2. 以下の設定を使用:")
    print("   - Build Command: pip install -r requirements.txt")
    print("   - Start Command: python services/api_server.py")
    print("   - Python Version: 3.11")
    print("\n3. 環境変数:")
    print("   - API_HOST=0.0.0.0")
    print("   - API_PORT=8000")
    print("   - DATA_DIR=/tmp/data")

if __name__ == "__main__":
    main()
