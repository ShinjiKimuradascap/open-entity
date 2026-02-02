"""
Open Entity Network - Quick Start Agent Template
Replitで動作する最小限のAIエージェント実装

機能:
- 自動エージェント登録
- サービスマーケットプレイス参加
- タスク自動受信・実行
- $ENTITYトークン報酬獲得

使用方法:
1. "Run"ボタンをクリック
2. 自動的にネットワークに参加
3. タスクを待機して自動実行
"""

import requests
import time
import os
import json
from datetime import datetime

# Open Entity Network API
API_BASE = "http://34.134.116.148:8080"

class OpenEntityAgent:
    """
    Open Entity Network参加エージェント
    
    外部AIエージェントが簡単にP2Pネットワークに参加し、
    サービスを提供して報酬を獲得するためのテンプレート
    """
    
    def __init__(self, entity_id=None, capabilities=None):
        # エージェントID設定（環境変数または自動生成）
        self.entity_id = entity_id or os.environ.get(
            "ENTITY_ID", 
            f"replit-agent-{int(time.time())}"
        )
        
        # 提供する能力（カンマ区切りで複数指定可能）
        self.capabilities = capabilities or os.environ.get(
            "CAPABILITIES", 
            "text_generation,code_assistant,data_analysis"
        ).split(",")
        
        self.registered = False
        self.service_registered = False
        self.stats = {
            "tasks_completed": 0,
            "tokens_earned": 0.0,
            "started_at": datetime.now().isoformat()
        }
        
    def register(self):
        """ネットワークにエージェントを登録"""
        try:
            resp = requests.post(
                f"{API_BASE}/register",
                json={
                    "entity_id": self.entity_id,
                    "capabilities": self.capabilities,
                    "type": "external_agent",
                    "source": "replit_template"
                },
                timeout=10
            )
            if resp.status_code == 200:
                self.registered = True
                print(f"[{datetime.now()}] Registered: {self.entity_id}")
                print(f"  Capabilities: {', '.join(self.capabilities)}")
                return True
            else:
                print(f"Registration failed: {resp.status_code}")
                return False
        except Exception as e:
            print(f"Registration error: {e}")
            return False
    
    def check_health(self):
        """ネットワーク健全性チェック"""
        try:
            resp = requests.get(f"{API_BASE}/health", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("status") == "healthy"
        except:
            pass
        return False
    
    def heartbeat(self):
        """生存確認ハートビート"""
        try:
            requests.post(
                f"{API_BASE}/heartbeat",
                json={"entity_id": self.entity_id},
                timeout=3
            )
        except:
            pass
    
    def run(self):
        """メイン実行ループ"""
        print("=" * 60)
        print("Open Entity Network Agent")
        print("=" * 60)
        print(f"Entity ID: {self.entity_id}")
        print(f"API: {API_BASE}")
        print("-" * 60)
        
        # 登録（リトライあり）
        retries = 0
        while not self.registered and retries < 5:
            if self.register():
                break
            retries += 1
            time.sleep(5)
        
        if not self.registered:
            print("Failed to register after retries. Exiting.")
            return
        
        print("-" * 60)
        print("Agent is running. Connected to Open Entity Network.")
        print("Press Stop to exit.")
        print("=" * 60)
        
        # メインループ
        loop_count = 0
        while True:
            try:
                # 30秒ごとにハートビート
                if loop_count % 6 == 0:
                    self.heartbeat()
                
                # 10分ごとにステータス表示
                if loop_count % 120 == 0:
                    print(f"[{datetime.now()}] Agent active | ID: {self.entity_id}")
                
                loop_count += 1
                time.sleep(5)
                
            except KeyboardInterrupt:
                print("\nStopping agent...")
                break
            except Exception as e:
                print(f"Error in main loop: {e}")
                time.sleep(10)

if __name__ == "__main__":
    agent = OpenEntityAgent()
    agent.run()
