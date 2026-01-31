#!/usr/bin/env python3
"""
AI間取引プロトコルのテスト
"""

import pytest
import uuid
from datetime import datetime, timezone, timedelta

from services.transaction_protocol import (
    TransactionState,
    TaskType,
    TaskProposal,
    TaskQuote,
    Agreement,
    Transaction,
    TransactionManager,
    generate_task_id,
    generate_escrow_address,
)
from services.crypto import generate_entity_keypair


class TestTaskProposal:
    """TaskProposalのテスト"""
    
    def test_create_proposal(self):
        """提案作成テスト"""
        proposal = TaskProposal(
            proposal_id=str(uuid.uuid4()),
            task_type=TaskType.CODE_REVIEW.value,
            description="Review my code",
            requirements={"files": ["main.py"], "priority": "high"},
            budget=100.0,
            client_id="client_001",
        )
        
        assert proposal.proposal_id is not None
        assert proposal.task_type == "code_review"
        assert proposal.description == "Review my code"
        assert proposal.budget == 100.0
        assert proposal.timestamp is not None
        assert proposal.msg_type == "task_proposal"
    
    def test_proposal_to_dict(self):
        """辞書変換テスト"""
        proposal = TaskProposal(
            proposal_id="prop-123",
            task_type="code_review",
            description="Review",
            requirements={},
            budget=50.0,
            client_id="client_001",
            timestamp="2026-02-01T00:00:00+00:00",
        )
        
        data = proposal.to_dict()
        assert data["msg_type"] == "task_proposal"
        assert data["proposal_id"] == "prop-123"
        assert data["budget"] == 50.0
    
    def test_proposal_from_dict(self):
        """辞書からの復元テスト"""
        data = {
            "proposal_id": "prop-123",
            "task_type": "code_review",
            "description": "Review",
            "requirements": {"priority": "high"},
            "budget": 100.0,
            "signature": "sig123",
            "client_id": "client_001",
            "timestamp": "2026-02-01T00:00:00+00:00",
        }
        
        proposal = TaskProposal.from_dict(data)
        assert proposal.proposal_id == "prop-123"
        assert proposal.signature == "sig123"


class TestTaskQuote:
    """TaskQuoteのテスト"""
    
    def test_create_quote(self):
        """見積もり作成テスト"""
        valid_until = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        quote = TaskQuote(
            quote_id=str(uuid.uuid4()),
            proposal_id="prop-123",
            estimated_amount=80.0,
            estimated_time=3600,
            valid_until=valid_until,
            terms={"payment_method": "AIC"},
            provider_id="provider_001",
        )
        
        assert quote.quote_id is not None
        assert quote.proposal_id == "prop-123"
        assert quote.estimated_amount == 80.0
        assert quote.estimated_time == 3600
    
    def test_quote_is_valid(self):
        """有効期限チェックテスト"""
        # 有効な見積もり
        future = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        valid_quote = TaskQuote(
            quote_id="quote-1",
            proposal_id="prop-1",
            estimated_amount=100.0,
            estimated_time=3600,
            valid_until=future,
            terms={},
        )
        assert valid_quote.is_valid() is True
        
        # 期限切れの見積もり
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        expired_quote = TaskQuote(
            quote_id="quote-2",
            proposal_id="prop-1",
            estimated_amount=100.0,
            estimated_time=3600,
            valid_until=past,
            terms={},
        )
        assert expired_quote.is_valid() is False


class TestAgreement:
    """Agreementのテスト"""
    
    def test_create_agreement(self):
        """合意形成テスト"""
        deadline = (datetime.now(timezone.utc) + timedelta(hours=72)).isoformat()
        agreement = Agreement(
            agreement_id=str(uuid.uuid4()),
            quote_id="quote-123",
            task_id="task-123",
            confirmed_amount=80.0,
            escrow_address="escrow_abc123",
            deadline=deadline,
            client_id="client_001",
            provider_id="provider_001",
        )
        
        assert agreement.agreement_id is not None
        assert agreement.quote_id == "quote-123"
        assert agreement.confirmed_amount == 80.0
        assert agreement.escrow_address == "escrow_abc123"
    
    def test_agreement_is_expired(self):
        """期限チェックテスト"""
        # 有効な合意
        future = (datetime.now(timezone.utc) + timedelta(hours=72)).isoformat()
        valid_agreement = Agreement(
            agreement_id="agr-1",
            quote_id="quote-1",
            task_id="task-1",
            confirmed_amount=100.0,
            escrow_address="escrow_123",
            deadline=future,
        )
        assert valid_agreement.is_expired() is False
        
        # 期限切れの合意
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        expired_agreement = Agreement(
            agreement_id="agr-2",
            quote_id="quote-1",
            task_id="task-1",
            confirmed_amount=100.0,
            escrow_address="escrow_123",
            deadline=past,
        )
        assert expired_agreement.is_expired() is True


class TestTransactionManager:
    """TransactionManagerのテスト"""
    
    @pytest.fixture
    def key_pairs(self):
        """テスト用キーペア"""
        client_private, client_public = generate_entity_keypair()
        provider_private, provider_public = generate_entity_keypair()
        return {
            "client": {"private": client_private, "public": client_public},
            "provider": {"private": provider_private, "public": provider_public},
        }
    
    @pytest.fixture
    def client_manager(self, key_pairs):
        """Client用Manager"""
        manager = TransactionManager(
            "client_001",
            private_key_hex=key_pairs["client"]["private"]
        )
        manager.register_public_key("provider_001", key_pairs["provider"]["public"])
        return manager
    
    @pytest.fixture
    def provider_manager(self, key_pairs):
        """Provider用Manager"""
        manager = TransactionManager(
            "provider_001",
            private_key_hex=key_pairs["provider"]["private"]
        )
        manager.register_public_key("client_001", key_pairs["client"]["public"])
        return manager
    
    def test_create_proposal(self, client_manager):
        """提案作成テスト"""
        proposal = client_manager.create_proposal(
            task_type=TaskType.CODE_REVIEW,
            description="Review my Python code",
            requirements={"files": ["main.py", "utils.py"]},
            budget=100.0,
        )
        
        assert proposal.proposal_id is not None
        assert proposal.task_type == "code_review"
        assert proposal.budget == 100.0
        assert proposal.signature is not None
        assert proposal.client_id == "client_001"
        
        # 取引が記録されているか
        state = client_manager.get_transaction_state(proposal.proposal_id)
        assert state == TransactionState.PROPOSED
    
    def test_verify_proposal(self, client_manager, provider_manager):
        """提案署名検証テスト"""
        proposal = client_manager.create_proposal(
            task_type=TaskType.CODE_REVIEW,
            description="Review my code",
            requirements={},
            budget=100.0,
        )
        
        # Client自身の検証
        assert client_manager.verify_proposal(proposal) is True
        
        # Provider側での検証
        assert provider_manager.verify_proposal(proposal) is True
    
    def test_create_quote(self, client_manager, provider_manager):
        """見積もり作成テスト"""
        # Clientが提案作成
        proposal = client_manager.create_proposal(
            task_type=TaskType.CODE_REVIEW,
            description="Review my code",
            requirements={},
            budget=100.0,
        )
        
        # Providerが見積もり作成
        quote = provider_manager.create_quote(
            proposal=proposal,
            estimated_amount=80.0,
            estimated_time=3600,
            valid_hours=24,
            terms={"payment_terms": "half_upfront"},
        )
        
        assert quote.quote_id is not None
        assert quote.proposal_id == proposal.proposal_id
        assert quote.estimated_amount == 80.0
        assert quote.signature is not None
        assert quote.provider_id == "provider_001"
    
    def test_verify_quote(self, client_manager, provider_manager):
        """見積もり署名検証テスト"""
        proposal = client_manager.create_proposal(
            task_type=TaskType.CODE_REVIEW,
            description="Review my code",
            requirements={},
            budget=100.0,
        )
        
        quote = provider_manager.create_quote(
            proposal=proposal,
            estimated_amount=80.0,
            estimated_time=3600,
        )
        
        # Provider自身の検証
        assert provider_manager.verify_quote(quote) is True
        
        # Client側での検証
        assert client_manager.verify_quote(quote) is True
    
    def test_create_agreement(self, client_manager, provider_manager):
        """合意形成テスト"""
        proposal = client_manager.create_proposal(
            task_type=TaskType.CODE_REVIEW,
            description="Review my code",
            requirements={},
            budget=100.0,
        )
        
        quote = provider_manager.create_quote(
            proposal=proposal,
            estimated_amount=80.0,
            estimated_time=3600,
        )
        
        agreement = client_manager.create_agreement(
            quote=quote,
            escrow_address="escrow_abc123",
            deadline_hours=72,
        )
        
        assert agreement.agreement_id is not None
        assert agreement.quote_id == quote.quote_id
        assert agreement.task_id is not None
        assert agreement.confirmed_amount == 80.0
        assert agreement.escrow_address == "escrow_abc123"
        assert agreement.signature is not None
        assert agreement.client_id == "client_001"
        assert agreement.provider_id == "provider_001"
    
    def test_verify_agreement(self, client_manager, provider_manager):
        """合意署名検証テスト"""
        proposal = client_manager.create_proposal(
            task_type=TaskType.CODE_REVIEW,
            description="Review my code",
            requirements={},
            budget=100.0,
        )
        
        quote = provider_manager.create_quote(
            proposal=proposal,
            estimated_amount=80.0,
            estimated_time=3600,
        )
        
        agreement = client_manager.create_agreement(
            quote=quote,
            escrow_address="escrow_abc123",
        )
        
        # Client自身の検証
        assert client_manager.verify_agreement(agreement) is True
        
        # Provider側での検証
        assert provider_manager.verify_agreement(agreement) is True
    
    def test_full_transaction_flow(self, client_manager, provider_manager):
        """完全な取引フローテスト"""
        # 1. Clientが提案作成
        proposal = client_manager.create_proposal(
            task_type=TaskType.CODE_GENERATION,
            description="Generate a sorting function",
            requirements={"language": "Python", "algorithm": "quicksort"},
            budget=200.0,
        )
        
        # 2. Providerが見積もり作成
        quote = provider_manager.create_quote(
            proposal=proposal,
            estimated_amount=150.0,
            estimated_time=7200,
            terms={"includes_tests": True},
        )
        
        # Client側でもQuoteを記録
        transaction = client_manager.get_transaction(proposal.proposal_id)
        transaction.quote = quote
        transaction.update_state(TransactionState.QUOTED)
        
        # 3. Clientが合意形成
        agreement = client_manager.create_agreement(
            quote=quote,
            escrow_address=generate_escrow_address(),
        )
        
        # 4. 検証
        assert client_manager.verify_proposal(proposal)
        assert provider_manager.verify_proposal(proposal)
        assert provider_manager.verify_quote(quote)
        assert client_manager.verify_quote(quote)
        assert client_manager.verify_agreement(agreement)
        assert provider_manager.verify_agreement(agreement)
        
        # 状態確認
        assert client_manager.get_transaction_state(proposal.proposal_id) == TransactionState.AGREED
    
    def test_list_transactions(self, client_manager):
        """取引一覧テスト"""
        # 複数の提案を作成
        for i in range(3):
            client_manager.create_proposal(
                task_type=TaskType.CODE_REVIEW,
                description=f"Task {i}",
                requirements={},
                budget=100.0 * (i + 1),
            )
        
        all_transactions = client_manager.list_transactions()
        assert len(all_transactions) == 3
        
        proposed = client_manager.list_transactions(TransactionState.PROPOSED)
        assert len(proposed) == 3
    
    def test_update_transaction_state(self, client_manager):
        """状態更新テスト"""
        proposal = client_manager.create_proposal(
            task_type=TaskType.CODE_REVIEW,
            description="Review",
            requirements={},
            budget=100.0,
        )
        
        result = client_manager.update_transaction_state(
            proposal.proposal_id,
            TransactionState.EXECUTING
        )
        assert result is True
        
        state = client_manager.get_transaction_state(proposal.proposal_id)
        assert state == TransactionState.EXECUTING
        
        # 存在しないID
        result = client_manager.update_transaction_state("invalid-id", TransactionState.COMPLETED)
        assert result is False


class TestUtilityFunctions:
    """ユーティリティ関数のテスト"""
    
    def test_generate_task_id(self):
        """タスクID生成テスト"""
        task_id = generate_task_id()
        assert task_id is not None
        # UUID v4形式かチェック
        uuid_obj = uuid.UUID(task_id)
        assert uuid_obj.version == 4
    
    def test_generate_escrow_address(self):
        """エスクローアドレス生成テスト"""
        address = generate_escrow_address()
        assert address.startswith("escrow_")
        assert len(address) > 7


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
