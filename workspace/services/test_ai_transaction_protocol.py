#!/usr/bin/env python3
"""
AI間取引プロトコル テスト
"""

import unittest
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).parent))

from ai_transaction_protocol import (
    TaskProposal, TaskQuote, Agreement,
    TransactionStatus, AITransactionManager, get_transaction_manager
)


class TestTaskProposal(unittest.TestCase):
    """TaskProposalのテスト"""
    
    def test_create_proposal(self):
        """提案作成"""
        proposal = TaskProposal(
            client_id="client_001",
            title="Code Review Request",
            description="Please review my Python code",
            budget_max=100.0,
            task_type="review",
            requirements=["Check for bugs", "Suggest improvements"]
        )
        
        self.assertIsNotNone(proposal.proposal_id)
        self.assertEqual(proposal.client_id, "client_001")
        self.assertEqual(proposal.title, "Code Review Request")
        self.assertEqual(proposal.budget_max, 100.0)
        self.assertEqual(len(proposal.requirements), 2)
        self.assertFalse(proposal.is_expired())
    
    def test_serialization(self):
        """シリアライズ/デシリアライズ"""
        proposal = TaskProposal(
            client_id="client_001",
            title="Test",
            description="Test description",
            budget_max=50.0
        )
        
        # to_dict -> from_dict
        data = proposal.to_dict()
        restored = TaskProposal.from_dict(data)
        
        self.assertEqual(restored.proposal_id, proposal.proposal_id)
        self.assertEqual(restored.client_id, proposal.client_id)
        self.assertEqual(restored.budget_max, proposal.budget_max)
        
        # JSON
        json_str = proposal.to_json()
        restored_json = TaskProposal.from_json(json_str)
        self.assertEqual(restored_json.title, proposal.title)


class TestTaskQuote(unittest.TestCase):
    """TaskQuoteのテスト"""
    
    def test_create_quote(self):
        """見積もり作成"""
        quote = TaskQuote(
            proposal_id="prop_001",
            provider_id="provider_001",
            estimated_amount=80.0,
            estimated_time_seconds=7200,
            terms={"revision_count": 2}
        )
        
        self.assertIsNotNone(quote.quote_id)
        self.assertEqual(quote.proposal_id, "prop_001")
        self.assertEqual(quote.provider_id, "provider_001")
        self.assertEqual(quote.estimated_amount, 80.0)
        self.assertEqual(quote.estimated_time_seconds, 7200)
        self.assertEqual(quote.terms["revision_count"], 2)


class TestAgreement(unittest.TestCase):
    """Agreementのテスト"""
    
    def test_create_agreement(self):
        """合意作成"""
        agreement = Agreement(
            quote_id="quote_001",
            proposal_id="prop_001",
            client_id="client_001",
            provider_id="provider_001",
            confirmed_amount=80.0
        )
        
        self.assertIsNotNone(agreement.agreement_id)
        self.assertIsNotNone(agreement.task_id)
        self.assertEqual(agreement.quote_id, "quote_001")
        self.assertEqual(agreement.client_id, "client_001")
        self.assertEqual(agreement.provider_id, "provider_001")
        self.assertEqual(agreement.confirmed_amount, 80.0)
        self.assertFalse(agreement.is_fully_signed())


class TestTransactionManager(unittest.TestCase):
    """AITransactionManagerのテスト"""
    
    def setUp(self):
        """テスト前準備"""
        self.manager = AITransactionManager()
    
    def test_full_transaction_flow(self):
        """完全な取引フロー"""
        # 1. Clientが提案を作成
        proposal = self.manager.create_proposal(
            client_id="client_001",
            title="Code Generation",
            description="Generate Python function",
            budget_max=100.0,
            task_type="code",
            requirements=["Clean code", "Type hints"]
        )
        self.assertIsNotNone(proposal)
        self.assertIn(proposal.proposal_id, self.manager._proposals)
        
        # 2. Providerが見積もりを返信
        quote = self.manager.create_quote(
            proposal_id=proposal.proposal_id,
            provider_id="provider_001",
            estimated_amount=80.0,
            estimated_time_seconds=3600,
            terms={"delivery_format": "python_file"}
        )
        self.assertIsNotNone(quote)
        self.assertIn(quote.quote_id, self.manager._quotes)
        
        # 3. Clientが合意を作成
        agreement = self.manager.create_agreement(quote.quote_id)
        self.assertIsNotNone(agreement)
        self.assertIn(agreement.agreement_id, self.manager._agreements)
        self.assertEqual(agreement.confirmed_amount, 80.0)
        
        # 4. 状態遷移
        status = self.manager.get_transaction_status(agreement.agreement_id)
        self.assertEqual(status, TransactionStatus.AGREED)
        
        # ESCROW_LOCKEDに更新
        self.assertTrue(
            self.manager.update_status(agreement.agreement_id, TransactionStatus.ESCROW_LOCKED)
        )
        status = self.manager.get_transaction_status(agreement.agreement_id)
        self.assertEqual(status, TransactionStatus.ESCROW_LOCKED)


class TestTransactionStatus(unittest.TestCase):
    """取引状態のテスト"""
    
    def test_status_values(self):
        """状態値の確認"""
        self.assertEqual(TransactionStatus.PROPOSED.value, "proposed")
        self.assertEqual(TransactionStatus.COMPLETED.value, "completed")
        self.assertEqual(TransactionStatus.RELEASED.value, "released")


if __name__ == "__main__":
    # テスト実行
    unittest.main(verbosity=2)
