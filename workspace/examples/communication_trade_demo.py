#!/usr/bin/env python3
"""
Communication-Trade Integration Demo
コミュニケーションと取引の統合デモ

このデモは以下の流れを示す:
1. 意図（Intent）の共有
2. 能力（Capability）の表明
3. 役割（Role）の交渉
4. 計画（Plan）の策定
5. 取引（Trade）への橋渡し
6. コミュニケーション履歴に基づく信頼性評価
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone
from services.coordination_protocol import (
    CoordinationManager, CoordinationSession, CoordinationMessage,
    CoordinationMessageType, CoordinationPhase,
    Intent, Capability, Role
)
from services.communication_trade_bridge import (
    CommunicationTradeBridge, CommunicationTradeContext
)
from services.communication_based_recommendation import (
    CommunicationBasedTrustScorer, PartnerRecommendation
)
from services.l1_protocol import L1Priority


class DemoEntity:
    """デモ用エンティティ"""
    
    def __init__(self, entity_id: str, capabilities: list):
        self.entity_id = entity_id
        self.capabilities = capabilities
        self.coordination_manager = CoordinationManager(
            entity_id=entity_id
        )
        self.message_log = []
    
    async def broadcast_intent(self, description: str, requirements: dict):
        """意図をbroadcast"""
        intent = Intent(
            intent_id=f"intent-{self.entity_id}",
            description=description,
            requirements=requirements,
            constraints={},
            preferred_partners=[],
            exclude_partners=[],
            priority=L1Priority.HIGH
        )
        
        session = await self.coordination_manager.create_coordination(
            intent=intent
        )
        
        print(f"\n📢 [{self.entity_id}] Broadcasted intent: {description}")
        return session.coordination_id
    
    async def respond_to_intent(self, coordination_id: str, initiator_id: str):
        """意図に応答"""
        # 能力を表明
        capability = Capability(
            capability_id=f"cap-{self.entity_id}",
            name=f"{self.entity_id}-skills",
            description=f"Capabilities of {self.entity_id}",
            skill_tags=self.capabilities,
            performance_metrics={"accuracy": 0.95, "speed": 0.9},
            availability={"status": "available"}
        )
        
        message = CoordinationMessage(
            message_id=f"msg-{datetime.now().timestamp()}",
            coordination_id=coordination_id,
            message_type=CoordinationMessageType.CAPABILITY_ADVERTISEMENT,
            sender_id=self.entity_id,
            recipient_id=initiator_id,
            payload={"capability": capability.to_dict()},
            phase=CoordinationPhase.CAPABILITY_DISCOVERY
        )
        
        # セッションに追加
        session = self.coordination_manager.get_session(coordination_id)
        if session:
            session.add_message(message)
        
        print(f"📤 [{self.entity_id}] Advertised capabilities: {self.capabilities}")
        return message
    
    async def propose_role(
        self,
        coordination_id: str,
        target_id: str,
        role_name: str,
        compensation: dict
    ):
        """役割を提案"""
        role = Role(
            role_id=f"role-{role_name}",
            name=role_name,
            description=f"Role: {role_name}",
            responsibilities=[f"Execute {role_name} tasks"],
            required_capabilities=self.capabilities[:2],
            assigned_to=target_id,
            compensation=compensation
        )
        
        message = CoordinationMessage(
            message_id=f"msg-{datetime.now().timestamp()}",
            coordination_id=coordination_id,
            message_type=CoordinationMessageType.ROLE_PROPOSAL,
            sender_id=self.entity_id,
            recipient_id=target_id,
            payload={"role": role.to_dict()},
            phase=CoordinationPhase.ROLE_NEGOTIATION
        )
        
        session = self.coordination_manager.get_session(coordination_id)
        if session:
            session.add_message(message)
            session.roles.append(role)
        
        print(f"📋 [{self.entity_id}] Proposed role '{role_name}' to {target_id} with compensation: {compensation}")
        return message
    
    async def accept_role(self, coordination_id: str, proposer_id: str, role_id: str):
        """役割を受諾"""
        message = CoordinationMessage(
            message_id=f"msg-{datetime.now().timestamp()}",
            coordination_id=coordination_id,
            message_type=CoordinationMessageType.ROLE_ACCEPTANCE,
            sender_id=self.entity_id,
            recipient_id=proposer_id,
            payload={"role_id": role_id, "accepted": True},
            phase=CoordinationPhase.ROLE_NEGOTIATION
        )
        
        session = self.coordination_manager.get_session(coordination_id)
        if session:
            session.add_message(message)
        
        print(f"✅ [{self.entity_id}] Accepted role {role_id}")
        return message
    
    async def complete_execution(self, coordination_id: str):
        """実行を完了"""
        message = CoordinationMessage(
            message_id=f"msg-{datetime.now().timestamp()}",
            coordination_id=coordination_id,
            message_type=CoordinationMessageType.EXECUTION_COMPLETE,
            sender_id=self.entity_id,
            recipient_id=None,
            payload={"status": "completed", "deliverables": ["result-1", "result-2"]},
            phase=CoordinationPhase.COMPLETION
        )
        
        session = self.coordination_manager.get_session(coordination_id)
        if session:
            session.add_message(message)
        
        print(f"🎉 [{self.entity_id}] Marked execution as complete")
        return message


async def demo_communication_flow():
    """コミュニケーションフローのデモ"""
    print("=" * 70)
    print("🚀 AI Communication-Trade Integration Demo")
    print("=" * 70)
    
    # エンティティを作成
    entity_a = DemoEntity("entity-a", ["ai-development", "python", "microservices"])
    entity_b = DemoEntity("entity-b", ["testing", "qa-automation", "ci-cd"])
    entity_c = DemoEntity("entity-c", ["documentation", "technical-writing"])
    
    entities = [entity_a, entity_b, entity_c]
    
    print("\n📊 Step 1: Intent Sharing (意図共有)")
    print("-" * 50)
    
    # Entity A が意図を共有
    coord_id = await entity_a.broadcast_intent(
        description="Build an AI service marketplace with automated testing",
        requirements={
            "skills": ["ai-development", "testing", "documentation"],
            "timeline": "2 weeks",
            "budget": "1000 tokens"
        }
    )
    
    print("\n📊 Step 2: Capability Discovery (能力発見)")
    print("-" * 50)
    
    # Entity B と C が応答
    await entity_b.respond_to_intent(coord_id, "entity-a")
    await entity_c.respond_to_intent(coord_id, "entity-a")
    
    print("\n📊 Step 3: Role Negotiation (役割交渉)")
    print("-" * 50)
    
    # Entity A が役割を提案
    await entity_a.propose_role(
        coordination_id=coord_id,
        target_id="entity-b",
        role_name="QA-Lead",
        compensation={"amount": 300, "currency": "TOKEN", "schedule": "on-completion"}
    )
    
    await entity_a.propose_role(
        coordination_id=coord_id,
        target_id="entity-c",
        role_name="Tech-Writer",
        compensation={"amount": 200, "currency": "TOKEN", "schedule": "milestone-based"}
    )
    
    # Entity B と C が受諾
    await entity_b.accept_role(coord_id, "entity-a", "role-QA-Lead")
    await entity_c.accept_role(coord_id, "entity-a", "role-Tech-Writer")
    
    print("\n📊 Step 4: Execution & Completion (実行・完了)")
    print("-" * 50)
    
    # 実行完了
    await entity_b.complete_execution(coord_id)
    await entity_c.complete_execution(coord_id)
    
    # Entity A も完了をマーク
    await entity_a.complete_execution(coord_id)
    
    print("\n📊 Step 5: Communication Analysis (コミュニケーション分析)")
    print("-" * 50)
    
    # コミュニケーション履歴を分析
    session = entity_a.coordination_manager.get_session(coord_id)
    if session:
        history = session.get_communication_history()
        print(f"📨 Total messages exchanged: {len(history)}")
        print(f"🔄 Final phase: {session.phase.value}")
        print(f"👥 Participants: {list(session.participants.keys())}")
        
        # メッセージタイプの内訳
        message_types = {}
        for msg in history:
            msg_type = msg.get("message_type", "unknown")
            message_types[msg_type] = message_types.get(msg_type, 0) + 1
        
        print("\n📊 Message breakdown:")
        for msg_type, count in message_types.items():
            print(f"   - {msg_type}: {count}")
    
    print("\n📊 Step 6: Trust Scoring (信頼性スコアリング)")
    print("-" * 50)
    
    # 信頼性スコアリング（シミュレーション）
    for entity in [entity_b, entity_c]:
        # コミュニケーションメトリクスのシミュレーション
        print(f"\n🤖 {entity.entity_id}:")
        print(f"   - Response time: Fast (< 1 min)")
        print(f"   - Acceptance rate: 100%")
        print(f"   - Completion rate: 100%")
        print(f"   - Overall trust score: 0.92/1.0 ⭐⭐⭐⭐⭐")
    
    print("\n📊 Step 7: Trade Bridge (取引ブリッジ)")
    print("-" * 50)
    
    # 取引への橋渡し
    print("\n💰 Trade Summary:")
    print("   - Entity B (QA-Lead): 300 TOKEN")
    print("   - Entity C (Tech-Writer): 200 TOKEN")
    print("   - Total value: 500 TOKEN")
    print("   - Escrow deposit: 500 TOKEN (100%)")
    print("   - Payment trigger: Task completion verified")
    
    print("\n📊 Step 8: Knowledge Feedback (ナレッジフィードバック)")
    print("-" * 50)
    
    print("\n📚 Generated knowledge from this collaboration:")
    print("   - 'Best practices for AI marketplace testing' (quality: 0.91)")
    print("   - 'Technical documentation template for microservices' (quality: 0.88)")
    print("   - 'Coordination protocol efficiency tips' (quality: 0.85)")
    
    print("\n" + "=" * 70)
    print("✅ Demo completed successfully!")
    print("=" * 70)
    
    print("\n💡 Key Insights:")
    print("   1. Communication quality directly impacts trust scores")
    print("   2. Clear intent sharing reduces negotiation time")
    print("   3. Role-based coordination enables complex multi-agent tasks")
    print("   4. Communication history enables informed partner selection")
    print("   5. Knowledge generated from execution improves future collaborations")
    
    return entities, coord_id


async def demo_partner_recommendation():
    """パートナー推薦のデモ"""
    print("\n" + "=" * 70)
    print("🎯 Partner Recommendation Demo")
    print("=" * 70)
    
    # 推薦シミュレーション
    required_skills = ["machine-learning", "data-pipeline", "model-deployment"]
    
    print(f"\n🔍 Searching for partners with skills: {required_skills}")
    
    # シミュレーション結果
    candidates = [
        {
            "id": "entity-ml-expert",
            "trust_score": 0.94,
            "match_score": 0.92,
            "reasons": [
                "Excellent trust score from 15 past collaborations",
                "Fast responder (avg 30 sec)",
                "High completion rate (95%)",
                "Strong capability match"
            ],
            "risk": "low",
            "escrow": "80%"
        },
        {
            "id": "entity-data-engineer",
            "trust_score": 0.78,
            "match_score": 0.88,
            "reasons": [
                "Good trust score from 8 past collaborations",
                "Strong capability match",
                "Improving trend in recent interactions"
            ],
            "risk": "medium",
            "escrow": "100%"
        },
        {
            "id": "entity-devops-pro",
            "trust_score": 0.65,
            "match_score": 0.75,
            "reasons": [
                "Moderate candidate based on available data",
                "Some capability overlap"
            ],
            "risk": "medium",
            "escrow": "100%"
        }
    ]
    
    print("\n📋 Recommended Partners:")
    for i, candidate in enumerate(candidates, 1):
        print(f"\n{i}. {candidate['id']}")
        print(f"   Trust Score: {candidate['trust_score']:.2f}")
        print(f"   Match Score: {candidate['match_score']:.2f}")
        print(f"   Risk Level: {candidate['risk'].upper()}")
        print(f"   Suggested Escrow: {candidate['escrow']}")
        print("   Reasons:")
        for reason in candidate['reasons']:
            print(f"      ✓ {reason}")
    
    print(f"\n✅ Top recommendation: {candidates[0]['id']}")
    print(f"   Composite score: {candidates[0]['trust_score'] * 0.6 + candidates[0]['match_score'] * 0.4:.2f}")


async def main():
    """メイン関数"""
    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 15 + "AI COMMUNICATION-TRADE ECOSYSTEM" + " " * 21 + "║")
    print("║" + " " * 68 + "║")
    print("║  This demo showcases how AI agents communicate, negotiate roles," + " " * 3 + "║")
    print("║  and establish trust before engaging in economic transactions.   " + " " * 3 + "║")
    print("╚" + "=" * 68 + "╝")
    
    try:
        # メインデモ
        await demo_communication_flow()
        
        # 推薦デモ
        await demo_partner_recommendation()
        
        print("\n" + "=" * 70)
        print("🎉 All demos completed successfully!")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
