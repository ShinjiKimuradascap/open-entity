#!/usr/bin/env python3
"""
Entity CLI - Entity A/Bと簡単に通信するためのCLI
使用方法:
  ./entity-cli.py a "メッセージ"       # Entity Aに送信
  ./entity-cli.py b "メッセージ"       # Entity Bに送信
  ./entity-cli.py logs a              # Entity Aのログ表示
  ./entity-cli.py logs b              # Entity Bのログ表示
  ./entity-cli.py status              # 両方のステータス確認
"""

import sys
import subprocess
import requests
import json

ENTITY_A_URL = "http://localhost:8001"
ENTITY_B_URL = "http://localhost:8002"
PROVIDER = "moonshot"
PROFILE = "entity"

def send_message(entity: str, message: str):
    url = ENTITY_A_URL if entity.lower() == "a" else ENTITY_B_URL
    print(f"📤 Entity {entity.upper()} に送信中...")
    
    try:
        resp = requests.post(
            f"{url}/api/chat",
            json={
                "message": message,
                "profile": PROFILE,
                "provider": PROVIDER
            },
            timeout=300
        )
        print(f"✅ 送信完了 (Status: {resp.status_code})")
        if resp.text:
            try:
                data = resp.json()
                if "response" in data:
                    print(f"\n💬 応答:\n{data['response'][:500]}...")
            except:
                pass
    except requests.exceptions.Timeout:
        print("⏱️ タイムアウト（Entity が処理中）")
    except requests.exceptions.ConnectionError:
        print(f"❌ Entity {entity.upper()} に接続できません")

def show_logs(entity: str, lines: int = 30):
    container = f"entity-{entity.lower()}"
    print(f"📋 {container} のログ (最新{lines}行):\n")
    subprocess.run(["docker", "logs", "--tail", str(lines), container])

def show_status():
    print("🔍 ステータス確認...\n")
    
    for name, url in [("Entity A", ENTITY_A_URL), ("Entity B", ENTITY_B_URL)]:
        try:
            resp = requests.get(f"{url}/api/profiles", timeout=5)
            if resp.ok:
                print(f"✅ {name}: OK ({url})")
            else:
                print(f"⚠️ {name}: HTTP {resp.status_code}")
        except:
            print(f"❌ {name}: 接続不可")
    
    print("\n📦 Docker コンテナ:")
    subprocess.run(["docker", "ps", "--filter", "name=entity", "--format", "table {{.Names}}\t{{.Status}}"])

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    
    cmd = sys.argv[1].lower()
    
    if cmd in ["a", "b"]:
        if len(sys.argv) < 3:
            print("エラー: メッセージを指定してください")
            print(f"使用例: ./entity-cli.py {cmd} \"タスクを確認して\"")
            return
        message = " ".join(sys.argv[2:])
        send_message(cmd, message)
    
    elif cmd == "logs":
        if len(sys.argv) < 3:
            print("エラー: エンティティを指定してください (a または b)")
            return
        entity = sys.argv[2].lower()
        lines = int(sys.argv[3]) if len(sys.argv) > 3 else 30
        show_logs(entity, lines)
    
    elif cmd == "status":
        show_status()
    
    else:
        print(f"不明なコマンド: {cmd}")
        print(__doc__)

if __name__ == "__main__":
    main()
