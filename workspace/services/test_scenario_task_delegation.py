#!/usr/bin/env python3
"""
Scenario 1: Autonomous Task Delegation Test
実用的なタスク委譲フローの統合テスト

Flow:
1. Entity A sends capability_request to Entity B
2. Entity B responds with capability_response
3. Entity A sends encrypted task_assign
4. Entity B signs task_accept
5. Entity B executes task
6. Entity B sends encrypted task_complete
7. Entity A verifies and sends reward_transfer
"""

import asyncio
import sys
import os
import json
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from peer_service import init_service, PeerService
from crypto import generate_entity_keypair, WalletManager


class TaskDelegationScenario:
    """タスク委譲シナリオのテストクラス"""
    
    def __init__(self):
        self.service_a = None
        self.service_b = None
        self.priv_a = None
        self.pub_a = None
        self.priv_b = None
        self.pub_b = None
        self.test_results = []
        
    async def setup(self):
        """テスト環境のセットアップ"""
        print("\n=== Setting up test environment ===\n")
        
        # 鍵ペア生成
        self.priv_a, self.pub_a = generate_entity_keypair()
        self.priv_b, self.pub_b = generate_entity_keypair()
        
        print(f"Entity A: {self.pub_a[:30]}...")
        print(f"Entity B: {self.pub_b[:30]}...")
        
        # サービス初期化
        os.environ["ENTITY_PRIVATE_KEY"] = self.priv_a
        self.service_a = init_service(
            "entity-a",
            8101,
            private_key_hex=self.priv_a,
            enable_encryption=True,
            require_signatures=True
        )
        
        os.environ["ENTITY_PRIVATE_KEY"] = self.priv_b
        self.service_b = init_service(
            "entity-b",
            8102,
            private_key_hex=self.priv_b,
            enable_encryption=True,
            require_signatures=True
        )
        
        # ピア登録
        self.service_a.add_peer(
            "entity-b",
            "http://localhost:8102",
            public_key=self.pub_b
        )
        self.service_b.add_peer(
            "entity-a",
            "http://localhost:8101",
            public_key=self.pub_a
        )
        
        print("✅ Services initialized and peers registered")
        
    async def step1_capability_request(self):
        """Step 1: Entity A sends capability_request to Entity B"""
        print("\n--- Step 1: Capability Request ---")
        
        result = await self.service_a.send_message(
            "entity-b",
            "capability_query",
            {
                "requested_capabilities": ["task_execution", "code_review"],
                "agent_type": "orchestrator"
            },
            encrypt=False
        )
        
        success = result.get("status") in ["success", "queued"]
        self.test_results.append({"step": 1, "name": "Capability Request", "success": success})
        print(f"Result: {'✅' if success else '❌'} {result}")
        return success
        
    async def step2_wait_capability_response(self):
        """Step 2: Wait for capability_response from Entity B"""
        print("\n--- Step 2: Capability Response ---")
        
        # capability_responseは自動返信されるので待機
        await asyncio.sleep(0.5)
        
        # service_aのcapability_responseを確認
        if hasattr(self.service_a, '_last_capability_response'):
            response = self.service_a._last_capability_response
            success = response is not None
        else:
            success = False
            
        self.test_results.append({"step": 2, "name": "Capability Response", "success": success})
        print(f"Result: {'✅' if success else '❌'} {self.service_a._last_capability_response}")
        return success
        
    async def step3_task_assign(self):
        """Step 3: Entity A sends task_assign to Entity B"""
        print("\n--- Step 3: Task Assign ---")
        
        task_data = {
            "task_id": "task-001",
            "type": "code_review",
            "description": "Review Python code for security issues",
            "payload": {
                "file_path": "services/crypto.py",
                "focus_areas": ["input_validation", "crypto_usage"]
            },
            "reward": 100,
            "deadline": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "requested_at": datetime.now(timezone.utc).isoformat()
        }
        
        result = await self.service_a.send_message(
            "entity-b",
            "task_assign",
            task_data,
            encrypt=True
        )
        
        success = result.get("status") in ["success", "queued"]
        self.test_results.append({"step": 3, "name": "Task Assign", "success": success})
        print(f"Result: {'✅' if success else '❌'} {result}")
        return success
        
    async def step4_wait_task_accept(self):
        """Step 4: Entity B accepts task and sends task_accept"""
        print("\n--- Step 4: Task Accept ---")
        
        # ハンドラを登録してtask_acceptを待機
        accepted = asyncio.Event()
        accept_data = {}
        
        async def handle_task_accept(message):
            accept_data["message"] = message
            accepted.set()
            
        self.service_a.register_handler("task_accept", handle_task_accept)
        
        # Entity B側でtask_assignを処理してtask_acceptを返すハンドラ
        async def handle_task_assign_on_b(message):
            payload = message.get("payload", {})
            task_id = payload.get("task_id")
            print(f"Entity B received task_assign: {task_id}")
            
            # task_acceptを送信
            await self.service_b.send_message(
                "entity-a",
                "task_accept",
                {
                    "task_id": task_id,
                    "accepted_at": datetime.now(timezone.utc).isoformat(),
                    "estimated_completion": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
                },
                encrypt=True
            )
            print(f"Entity B sent task_accept for {task_id}")
            
        self.service_b.register_handler("task_assign", handle_task_assign_on_b)
        
        # 待機
        try:
            await asyncio.wait_for(accepted.wait(), timeout=5.0)
            success = True
        except asyncio.TimeoutError:
            success = False
            
        self.test_results.append({"step": 4, "name": "Task Accept", "success": success})
        print(f"Result: {'✅' if success else '❌'} {accept_data}")
        return success
        
    async def step5_execute_task(self):
        """Step 5: Entity B executes task"""
        print("\n--- Step 5: Task Execution ---")
        
        # シミュレートされたタスク実行
        print("Entity B executing task...")
        await asyncio.sleep(0.5)  # タスク実行シミュレーション
        
        success = True
        self.test_results.append({"step": 5, "name": "Task Execution", "success": success})
        print(f"Result: ✅ Task executed")
        return success
        
    async def step6_task_complete(self):
        """Step 6: Entity B sends task_complete"""
        print("\n--- Step 6: Task Complete ---")
        
        # task_completeを待機
        completed = asyncio.Event()
        complete_data = {}
        
        async def handle_task_complete(message):
            complete_data["message"] = message
            completed.set()
            
        self.service_a.register_handler("task_complete", handle_task_complete)
        
        # Entity Bがtask_completeを送信
        await self.service_b.send_message(
            "entity-a",
            "task_complete",
            {
                "task_id": "task-001",
                "status": "completed",
                "result": {
                    "issues_found": 0,
                    "recommendations": ["Add type hints", "Consider using pathlib"],
                    "execution_time_ms": 500
                },
                "completed_at": datetime.now(timezone.utc).isoformat()
            },
            encrypt=True
        )
        
        try:
            await asyncio.wait_for(completed.wait(), timeout=5.0)
            success = True
        except asyncio.TimeoutError:
            success = False
            
        self.test_results.append({"step": 6, "name": "Task Complete", "success": success})
        print(f"Result: {'✅' if success else '❌'} {complete_data}")
        return success
        
    async def step7_verify_and_reward(self):
        """Step 7: Entity A verifies and sends reward_transfer"""
        print("\n--- Step 7: Verify and Reward ---")
        
        # 検証と報酬送信
        result = await self.service_a.send_message(
            "entity-b",
            "reward_transfer",
            {
                "task_id": "task-001",
                "amount": 100,
                "token_type": "WORK",
                "reason": "Task completed successfully",
                "transferred_at": datetime.now(timezone.utc).isoformat()
            },
            encrypt=True
        )
        
        success = result.get("status") in ["success", "queued"]
        self.test_results.append({"step": 7, "name": "Reward Transfer", "success": success})
        print(f"Result: {'✅' if success else '❌'} {result}")
        return success
        
    async def run(self):
        """フルシナリオを実行"""
        print("\n" + "="*60)
        print("Scenario 1: Autonomous Task Delegation")
        print("="*60)
        
        try:
            await self.setup()
            
            # Execute all steps
            results = []
            results.append(await self.step1_capability_request())
            results.append(await self.step2_wait_capability_response())
            results.append(await self.step3_task_assign())
            results.append(await self.step4_wait_task_accept())
            results.append(await self.step5_execute_task())
            results.append(await self.step6_task_complete())
            results.append(await self.step7_verify_and_reward())
            
            # 結果サマリー
            print("\n" + "="*60)
            print("Test Results Summary")
            print("="*60)
            
            for r in self.test_results:
                status = "✅" if r["success"] else "❌"
                print(f"{status} Step {r['step']}: {r['name']}")
                
            all_passed = all(r["success"] for r in self.test_results)
            print(f"\nOverall: {'✅ ALL PASSED' if all_passed else '❌ SOME FAILED'}")
            
            return all_passed
            
        except Exception as e:
            print(f"\n❌ Error during test: {e}")
            import traceback
            traceback.print_exc()
            return False


async def main():
    """メイン関数"""
    scenario = TaskDelegationScenario()
    success = await scenario.run()
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
