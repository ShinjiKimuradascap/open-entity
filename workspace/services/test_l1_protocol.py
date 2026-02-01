#!/usr/bin/env python3
"""
Unit tests for L1 AI Communication Protocol v0.1
Covers: L1Message base class, task delegation, responses, status updates, payments, protocol handler
"""

import os
import sys
import json
import base64
import uuid
import time
from datetime import datetime, timezone, timedelta
from unittest import mock

import pytest

pytestmark = pytest.mark.unit

# Add services directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from l1_protocol import (
    L1Message,
    L1TaskDelegation,
    L1DelegationResponse,
    L1StatusUpdate,
    L1Payment,
    L1ProtocolHandler,
    L1MessageType,
    L1TaskStatus,
    L1ResponseType,
    L1Priority,
    L1PaymentStatus,
    PROTOCOL_NAME,
    PROTOCOL_VERSION,
    create_agent_sender,
    create_agent_recipient,
    get_current_timestamp,
)

# Import crypto for signing tests
try:
    from crypto import (
        KeyPair,
        MessageSigner,
        SignatureVerifier,
        generate_entity_keypair,
    )
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

pytestmark = pytest.mark.unit


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sender_info():
    """Create test sender info"""
    return {
        'agent_id': 'agent-sender-001',
        'public_key': 'a' * 64  # Fake public key for testing
    }


@pytest.fixture
def recipient_info():
    """Create test recipient info"""
    return {
        'agent_id': 'agent-recipient-001',
        'public_key': 'b' * 64  # Fake public key for testing
    }


@pytest.fixture
def valid_keypair():
    """Generate a valid Ed25519 keypair for signing tests"""
    if CRYPTO_AVAILABLE:
        return generate_entity_keypair()
    return None


@pytest.fixture
def message_signer(valid_keypair):
    """Create a MessageSigner for testing"""
    if CRYPTO_AVAILABLE and valid_keypair:
        private_hex, _ = valid_keypair
        kp = KeyPair.from_private_key_hex(private_hex)
        return MessageSigner(kp)
    return None


# ============================================================================
# Test L1Message Base Class
# ============================================================================

class TestL1MessageBase:
    """Tests for L1Message base class"""

    def test_message_default_values(self):
        """Test that message has correct default values"""
        msg = L1Message()
        
        assert msg.protocol == PROTOCOL_NAME
        assert msg.version == PROTOCOL_VERSION
        assert msg.message_id is not None
        assert msg.timestamp is not None
        assert msg.sender == {}
        assert msg.recipient == {}
        assert msg.message_type == ""
        assert msg.payload == {}
        assert msg.signature is None
        assert msg.valid_until is not None
    
    def test_message_id_is_uuid_v4(self):
        """Test that message_id is a valid UUID v4"""
        msg = L1Message()
        
        # Should be valid UUID
        parsed_uuid = uuid.UUID(msg.message_id)
        assert parsed_uuid.version == 4
    
    def test_timestamp_is_iso8601(self):
        """Test that timestamp is valid ISO8601 format"""
        msg = L1Message()
        
        # Should be parseable as ISO8601
        parsed = datetime.fromisoformat(msg.timestamp.replace('Z', '+00:00'))
        assert parsed.tzinfo is not None
    
    def test_to_dict_conversion(self):
        """Test conversion to dictionary"""
        msg = L1Message(
            sender={'agent_id': 'sender-1'},
            recipient={'agent_id': 'recipient-1'},
            message_type='TEST',
            payload={'data': 'value'}
        )
        
        d = msg.to_dict()
        assert d['protocol'] == PROTOCOL_NAME
        assert d['version'] == PROTOCOL_VERSION
        assert d['sender']['agent_id'] == 'sender-1'
        assert d['recipient']['agent_id'] == 'recipient-1'
        assert d['message_type'] == 'TEST'
        assert d['payload']['data'] == 'value'
    
    def test_to_json_serialization(self):
        """Test JSON serialization"""
        msg = L1Message(
            sender={'agent_id': 'sender-1'},
            recipient={'agent_id': 'recipient-1'},
            message_type='TEST',
            payload={'data': 'value'}
        )
        
        json_str = msg.to_json()
        
        # Should be valid JSON
        parsed = json.loads(json_str)
        assert parsed['protocol'] == PROTOCOL_NAME
        assert parsed['sender']['agent_id'] == 'sender-1'
    
    def test_from_dict_deserialization(self):
        """Test deserialization from dictionary"""
        data = {
            'protocol': PROTOCOL_NAME,
            'version': PROTOCOL_VERSION,
            'message_id': str(uuid.uuid4()),
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'sender': {'agent_id': 'sender-1'},
            'recipient': {'agent_id': 'recipient-1'},
            'message_type': 'TEST',
            'payload': {'data': 'value'},
            'signature': None,
            'valid_until': (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        }
        
        msg = L1Message.from_dict(data)
        
        assert msg.protocol == PROTOCOL_NAME
        assert msg.sender['agent_id'] == 'sender-1'
        assert msg.payload['data'] == 'value'
    
    def test_from_json_deserialization(self):
        """Test deserialization from JSON"""
        original = L1Message(
            sender={'agent_id': 'sender-1'},
            recipient={'agent_id': 'recipient-1'},
            message_type='TEST',
            payload={'data': 'value'}
        )
        
        json_str = original.to_json()
        parsed = L1Message.from_json(json_str)
        
        assert parsed.message_id == original.message_id
        assert parsed.sender == original.sender
        assert parsed.payload == original.payload
    
    def test_to_bytes_for_signing(self):
        """Test canonical bytes representation for signing"""
        msg = L1Message(
            sender={'agent_id': 'sender-1'},
            recipient={'agent_id': 'recipient-1'},
            message_type='TEST',
            payload={'data': 'value'},
            signature='test-signature'
        )
        
        bytes_data = msg.to_bytes()
        
        # Should be valid UTF-8
        decoded = bytes_data.decode('utf-8')
        
        # Should NOT contain signature (it's for signing)
        assert 'test-signature' not in decoded
        
        # Should contain other fields
        assert 'sender-1' in decoded
        assert 'TEST' in decoded
    
    def test_get_sender_recipient_id(self):
        """Test sender/recipient ID getters"""
        msg = L1Message(
            sender={'agent_id': 'sender-1'},
            recipient={'agent_id': 'recipient-1'}
        )
        
        assert msg.get_sender_id() == 'sender-1'
        assert msg.get_recipient_id() == 'recipient-1'
    
    def test_get_sender_recipient_id_empty(self):
        """Test getters with empty sender/recipient"""
        msg = L1Message()
        
        assert msg.get_sender_id() is None
        assert msg.get_recipient_id() is None


# ============================================================================
# Test L1Message Validation
# ============================================================================

class TestL1MessageValidation:
    """Tests for message validation"""

    def test_valid_message(self, sender_info, recipient_info):
        """Test validation of a valid message"""
        msg = L1Message(
            sender=sender_info,
            recipient=recipient_info,
            message_type='TEST'
        )
        
        is_valid, error = msg.is_valid()
        assert is_valid is True
        assert error is None
    
    def test_invalid_protocol(self, sender_info, recipient_info):
        """Test validation fails with wrong protocol"""
        msg = L1Message(
            protocol='wrong-protocol',
            sender=sender_info,
            recipient=recipient_info,
            message_type='TEST'
        )
        
        is_valid, error = msg.is_valid()
        assert is_valid is False
        assert 'protocol' in error.lower()
    
    def test_invalid_version(self, sender_info, recipient_info):
        """Test validation fails with wrong version"""
        msg = L1Message(
            version='99.9',
            sender=sender_info,
            recipient=recipient_info,
            message_type='TEST'
        )
        
        is_valid, error = msg.is_valid()
        assert is_valid is False
        assert 'version' in error.lower()
    
    def test_invalid_message_id(self, sender_info, recipient_info):
        """Test validation fails with invalid message_id"""
        msg = L1Message(
            sender=sender_info,
            recipient=recipient_info,
            message_type='TEST',
            message_id='not-a-valid-uuid'
        )
        
        is_valid, error = msg.is_valid()
        assert is_valid is False
        assert 'message_id' in error.lower()
    
    def test_invalid_timestamp(self, sender_info, recipient_info):
        """Test validation fails with invalid timestamp"""
        msg = L1Message(
            sender=sender_info,
            recipient=recipient_info,
            message_type='TEST',
            timestamp='not-a-timestamp'
        )
        
        is_valid, error = msg.is_valid()
        assert is_valid is False
        assert 'timestamp' in error.lower()
    
    def test_missing_sender_agent_id(self, recipient_info):
        """Test validation fails without sender agent_id"""
        msg = L1Message(
            sender={},
            recipient=recipient_info,
            message_type='TEST'
        )
        
        is_valid, error = msg.is_valid()
        assert is_valid is False
        assert 'sender' in error.lower()
    
    def test_missing_recipient_agent_id(self, sender_info):
        """Test validation fails without recipient agent_id"""
        msg = L1Message(
            sender=sender_info,
            recipient={},
            message_type='TEST'
        )
        
        is_valid, error = msg.is_valid()
        assert is_valid is False
        assert 'recipient' in error.lower()
    
    def test_missing_message_type(self, sender_info, recipient_info):
        """Test validation fails without message_type"""
        msg = L1Message(
            sender=sender_info,
            recipient=recipient_info,
            message_type=''
        )
        
        is_valid, error = msg.is_valid()
        assert is_valid is False
        assert 'message_type' in error.lower()
    
    def test_expired_message(self, sender_info, recipient_info):
        """Test validation fails for expired message"""
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        msg = L1Message(
            sender=sender_info,
            recipient=recipient_info,
            message_type='TEST',
            valid_until=past
        )
        
        is_valid, error = msg.is_valid()
        assert is_valid is False
        assert 'expired' in error.lower()
    
    def test_is_expired_check(self):
        """Test explicit expiration check"""
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        
        valid_msg = L1Message(valid_until=future)
        expired_msg = L1Message(valid_until=past)
        
        assert valid_msg.is_expired() is False
        assert expired_msg.is_expired() is True


# ============================================================================
# Test Message Signing (if crypto available)
# ============================================================================

class TestL1MessageSigning:
    """Tests for message signing and verification"""

    @pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="Crypto not available")
    def test_sign_message(self, message_signer, sender_info, recipient_info):
        """Test signing a message"""
        msg = L1Message(
            sender=sender_info,
            recipient=recipient_info,
            message_type='TEST',
            payload={'data': 'value'}
        )
        
        assert msg.signature is None
        
        msg.sign(message_signer)
        
        assert msg.signature is not None
        assert len(msg.signature) > 0
        # Should be base64
        decoded = base64.b64decode(msg.signature)
        assert len(decoded) == 64  # Ed25519 signature is 64 bytes
    
    @pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="Crypto not available")
    def test_verify_signature_success(self, message_signer, sender_info, recipient_info, valid_keypair):
        """Test successful signature verification"""
        msg = L1Message(
            sender=sender_info,
            recipient=recipient_info,
            message_type='TEST',
            payload={'data': 'value'}
        )
        
        msg.sign(message_signer)
        
        # Create verifier with public key
        _, public_hex = valid_keypair
        public_key = bytes.fromhex(public_hex)
        verifier = SignatureVerifier(public_key)
        
        is_valid = msg.verify_signature(verifier)
        assert is_valid is True
    
    @pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="Crypto not available")
    def test_verify_signature_failure_wrong_key(self, message_signer, sender_info, recipient_info):
        """Test verification fails with wrong key"""
        msg = L1Message(
            sender=sender_info,
            recipient=recipient_info,
            message_type='TEST',
            payload={'data': 'value'}
        )
        
        msg.sign(message_signer)
        
        # Create verifier with different key
        other_keypair = generate_entity_keypair()
        _, other_public = other_keypair
        wrong_verifier = SignatureVerifier(bytes.fromhex(other_public))
        
        is_valid = msg.verify_signature(wrong_verifier)
        assert is_valid is False
    
    @pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="Crypto not available")
    def test_verify_signature_no_signature(self, sender_info, recipient_info, valid_keypair):
        """Test verification fails without signature"""
        msg = L1Message(
            sender=sender_info,
            recipient=recipient_info,
            message_type='TEST',
            payload={'data': 'value'}
        )
        
        _, public_hex = valid_keypair
        verifier = SignatureVerifier(bytes.fromhex(public_hex))
        
        is_valid = msg.verify_signature(verifier)
        assert is_valid is False
    
    @pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="Crypto not available")
    def test_signature_tampering_detection(self, message_signer, sender_info, recipient_info):
        """Test detection of tampered message after signing"""
        msg = L1Message(
            sender=sender_info,
            recipient=recipient_info,
            message_type='TEST',
            payload={'data': 'value'}
        )
        
        msg.sign(message_signer)
        
        # Tamper with payload
        msg.payload['data'] = 'tampered'
        
        # Verify original signature (should fail)
        _, public_hex = generate_entity_keypair()
        verifier = SignatureVerifier(bytes.fromhex(public_hex))
        
        # Actually use correct key
        kp = KeyPair.from_private_key_hex(generate_entity_keypair()[0])
        signer = MessageSigner(kp)
        msg2 = L1Message(
            sender=sender_info,
            recipient=recipient_info,
            message_type='TEST',
            payload={'data': 'value'}
        )
        msg2.sign(signer)
        msg2.payload['data'] = 'tampered'
        
        verifier2 = SignatureVerifier(kp.public_key)
        is_valid = msg2.verify_signature(verifier2)
        assert is_valid is False


# ============================================================================
# Test L1TaskDelegation
# ============================================================================

class TestL1TaskDelegation:
    """Tests for task delegation messages"""

    def test_create_task_delegation(self):
        """Test creating a task delegation message"""
        msg = L1TaskDelegation.create(
            sender_id='agent-a',
            recipient_id='agent-b',
            title='Test Task',
            description='Do something important',
            requirements=['req1', 'req2'],
            priority='high',
            reward_amount=100.0
        )
        
        assert msg.message_type == L1MessageType.TASK_DELEGATION.value
        assert msg.get_task_id() is not None
        assert msg.get_title() == 'Test Task'
        assert msg.sender['agent_id'] == 'agent-a'
        assert msg.recipient['agent_id'] == 'agent-b'
        assert msg.payload['description'] == 'Do something important'
        assert msg.payload['requirements'] == ['req1', 'req2']
        assert msg.payload['priority'] == 'high'
        assert msg.payload['reward_amount'] == 100.0
        assert msg.payload['reward_token'] == 'AIC'
    
    def test_task_delegation_defaults(self):
        """Test task delegation with default values"""
        msg = L1TaskDelegation.create(
            sender_id='agent-a',
            recipient_id='agent-b',
            title='Simple Task',
            description='Just do it'
        )
        
        assert msg.payload['task_type'] == 'custom'
        assert msg.payload['priority'] == 'normal'
        assert msg.payload['reward_amount'] == 0.0
        assert msg.payload['requirements'] == []
    
    def test_task_delegation_with_optional_fields(self):
        """Test task delegation with all optional fields"""
        deadline = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        
        msg = L1TaskDelegation.create(
            sender_id='agent-a',
            recipient_id='agent-b',
            title='Complex Task',
            description='Do something complex',
            task_type='code_review',
            constraints={'max_lines': 500},
            deliverables=['report.md', 'code.py'],
            deadline=deadline,
            estimated_hours=8,
            escrow_address='escrow-123',
            dependencies=['task-1', 'task-2'],
            required_capabilities=['python', 'crypto']
        )
        
        assert msg.payload['task_type'] == 'code_review'
        assert msg.payload['constraints']['max_lines'] == 500
        assert len(msg.payload['deliverables']) == 2
        assert msg.payload['deadline'] == deadline
        assert msg.payload['estimated_hours'] == 8
        assert msg.payload['escrow_address'] == 'escrow-123'
        assert len(msg.payload['dependencies']) == 2
        assert len(msg.payload['required_capabilities']) == 2
    
    def test_task_delegation_status_default(self):
        """Test that task status defaults to pending"""
        msg = L1TaskDelegation.create(
            sender_id='agent-a',
            recipient_id='agent-b',
            title='Test',
            description='Test'
        )
        
        assert msg.payload['status'] == L1TaskStatus.PENDING.value
    
    def test_task_delegation_get_priority(self):
        """Test get_priority method"""
        msg_high = L1TaskDelegation.create(
            sender_id='agent-a',
            recipient_id='agent-b',
            title='Test',
            description='Test',
            priority='high'
        )
        
        msg_critical = L1TaskDelegation.create(
            sender_id='agent-a',
            recipient_id='agent-b',
            title='Test',
            description='Test',
            priority='critical'
        )
        
        assert msg_high.get_priority() == L1Priority.HIGH
        assert msg_critical.get_priority() == L1Priority.CRITICAL
    
    def test_task_delegation_is_expired(self):
        """Test task deadline expiration check"""
        past_deadline = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        future_deadline = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        
        expired_msg = L1TaskDelegation.create(
            sender_id='agent-a',
            recipient_id='agent-b',
            title='Test',
            description='Test',
            deadline=past_deadline
        )
        
        valid_msg = L1TaskDelegation.create(
            sender_id='agent-a',
            recipient_id='agent-b',
            title='Test',
            description='Test',
            deadline=future_deadline
        )
        
        assert expired_msg.is_expired() is True
        assert valid_msg.is_expired() is False
    
    def test_task_delegation_validation(self):
        """Test task delegation validation"""
        msg = L1TaskDelegation.create(
            sender_id='agent-a',
            recipient_id='agent-b',
            title='Test',
            description='Test'
        )
        
        is_valid, error = msg.is_valid()
        assert is_valid is True


# ============================================================================
# Test L1DelegationResponse
# ============================================================================

class TestL1DelegationResponse:
    """Tests for delegation response messages"""

    def test_create_accept_response(self):
        """Test creating an acceptance response"""
        msg = L1DelegationResponse.create(
            task_id='task-123',
            sender_id='agent-b',
            recipient_id='agent-a',
            response_type=L1ResponseType.ACCEPT,
            message='Task accepted'
        )
        
        assert msg.message_type == L1MessageType.DELEGATION_RESPONSE.value
        assert msg.get_task_id() == 'task-123'
        assert msg.get_response_type() == L1ResponseType.ACCEPT
        assert msg.is_accepted() is True
        assert msg.sender['agent_id'] == 'agent-b'
        assert msg.recipient['agent_id'] == 'agent-a'
    
    def test_create_reject_response(self):
        """Test creating a rejection response"""
        msg = L1DelegationResponse.create(
            task_id='task-123',
            sender_id='agent-b',
            recipient_id='agent-a',
            response_type=L1ResponseType.REJECT,
            message='Cannot do this',
            rejection_reason='Insufficient resources'
        )
        
        assert msg.get_response_type() == L1ResponseType.REJECT
        assert msg.is_accepted() is False
        assert msg.payload['rejection_reason'] == 'Insufficient resources'
    
    def test_create_counter_response(self):
        """Test creating a counter-offer response"""
        msg = L1DelegationResponse.create(
            task_id='task-123',
            sender_id='agent-b',
            recipient_id='agent-a',
            response_type=L1ResponseType.COUNTER,
            message='Proposing different terms',
            counter_offer={'new_reward': 150.0},
            proposed_reward=150.0,
            estimated_start='2024-01-15T10:00:00Z',
            estimated_completion='2024-01-15T18:00:00Z'
        )
        
        assert msg.get_response_type() == L1ResponseType.COUNTER
        assert msg.is_accepted() is False
        assert msg.payload['counter_offer']['new_reward'] == 150.0
        assert msg.payload['proposed_reward'] == 150.0
        assert 'estimated_start' in msg.payload
    
    def test_create_defer_response(self):
        """Test creating a defer response"""
        msg = L1DelegationResponse.create(
            task_id='task-123',
            sender_id='agent-b',
            recipient_id='agent-a',
            response_type=L1ResponseType.DEFER,
            message='Need more time to decide'
        )
        
        assert msg.get_response_type() == L1ResponseType.DEFER
        assert msg.is_accepted() is False
    
    def test_accept_convenience_method(self):
        """Test the accept() convenience method"""
        msg = L1DelegationResponse.accept(
            task_id='task-123',
            sender_id='agent-b',
            recipient_id='agent-a',
            message='Happy to help'
        )
        
        assert msg.get_response_type() == L1ResponseType.ACCEPT
        assert msg.is_accepted() is True
        assert msg.payload['message'] == 'Happy to help'
    
    def test_reject_convenience_method(self):
        """Test the reject() convenience method"""
        msg = L1DelegationResponse.reject(
            task_id='task-123',
            sender_id='agent-b',
            recipient_id='agent-a',
            reason='Too busy',
            message='Maybe next time'
        )
        
        assert msg.get_response_type() == L1ResponseType.REJECT
        assert msg.is_accepted() is False
        assert msg.payload['rejection_reason'] == 'Too busy'
    
    def test_response_validation(self):
        """Test response message validation"""
        msg = L1DelegationResponse.accept(
            task_id='task-123',
            sender_id='agent-b',
            recipient_id='agent-a'
        )
        
        is_valid, error = msg.is_valid()
        assert is_valid is True
    
    def test_response_type_case_insensitive(self):
        """Test response type parsing is case insensitive"""
        msg = L1Message.from_dict({
            'protocol': PROTOCOL_NAME,
            'version': PROTOCOL_VERSION,
            'message_id': str(uuid.uuid4()),
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'sender': {'agent_id': 'sender'},
            'recipient': {'agent_id': 'recipient'},
            'message_type': L1MessageType.DELEGATION_RESPONSE.value,
            'payload': {'task_id': 't1', 'response_type': 'ACCEPT'},
            'valid_until': (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        })
        
        # Convert to L1DelegationResponse
        response = L1DelegationResponse.from_dict(msg.to_dict())
        assert response.get_response_type() == L1ResponseType.ACCEPT


# ============================================================================
# Test L1StatusUpdate
# ============================================================================

class TestL1StatusUpdate:
    """Tests for status update messages"""

    def test_create_status_update(self):
        """Test creating a status update message"""
        msg = L1StatusUpdate.create(
            task_id='task-123',
            sender_id='agent-b',
            recipient_id='agent-a',
            status=L1TaskStatus.RUNNING,
            progress_percent=50,
            message='Halfway done'
        )
        
        assert msg.message_type == L1MessageType.STATUS_UPDATE.value
        assert msg.get_task_id() == 'task-123'
        assert msg.get_status() == L1TaskStatus.RUNNING
        assert msg.get_progress() == 50
        assert msg.payload['message'] == 'Halfway done'
    
    def test_status_update_progress_clamping(self):
        """Test progress percentage is clamped to 0-100"""
        msg_low = L1StatusUpdate.create(
            task_id='task-123',
            sender_id='agent-b',
            recipient_id='agent-a',
            status=L1TaskStatus.PENDING,
            progress_percent=-10
        )
        
        msg_high = L1StatusUpdate.create(
            task_id='task-123',
            sender_id='agent-b',
            recipient_id='agent-a',
            status=L1TaskStatus.COMPLETED,
            progress_percent=150
        )
        
        assert msg_low.get_progress() == 0
        assert msg_high.get_progress() == 100
    
    def test_status_update_with_optional_fields(self):
        """Test status update with optional fields"""
        msg = L1StatusUpdate.create(
            task_id='task-123',
            sender_id='agent-b',
            recipient_id='agent-a',
            status=L1TaskStatus.RUNNING,
            progress_percent=75,
            deliverables_ready=['file1.py', 'file2.py'],
            issues=['Minor bug found'],
            eta='2024-01-15T18:00:00Z'
        )
        
        assert len(msg.payload['deliverables_ready']) == 2
        assert len(msg.payload['issues']) == 1
        assert msg.payload['eta'] == '2024-01-15T18:00:00Z'
    
    def test_status_update_status_transitions(self):
        """Test various status values"""
        statuses = [
            L1TaskStatus.PENDING,
            L1TaskStatus.ACCEPTED,
            L1TaskStatus.RUNNING,
            L1TaskStatus.COMPLETED,
            L1TaskStatus.FAILED,
            L1TaskStatus.REJECTED,
            L1TaskStatus.CANCELLED,
            L1TaskStatus.TIMEOUT,
        ]
        
        for status in statuses:
            msg = L1StatusUpdate.create(
                task_id='task-123',
                sender_id='agent-b',
                recipient_id='agent-a',
                status=status
            )
            assert msg.get_status() == status
    
    def test_status_update_validation(self):
        """Test status update validation"""
        msg = L1StatusUpdate.create(
            task_id='task-123',
            sender_id='agent-b',
            recipient_id='agent-a',
            status=L1TaskStatus.RUNNING,
            progress_percent=50
        )
        
        is_valid, error = msg.is_valid()
        assert is_valid is True


# ============================================================================
# Test L1Payment
# ============================================================================

class TestL1Payment:
    """Tests for payment messages"""

    def test_create_payment(self):
        """Test creating a payment message"""
        msg = L1Payment.create(
            task_id='task-123',
            sender_id='agent-a',
            recipient_id='agent-b',
            amount=100.0,
            token='AIC'
        )
        
        assert msg.message_type == L1MessageType.PAYMENT.value
        assert msg.get_payment_id() is not None
        assert msg.get_task_id() == 'task-123'
        assert msg.get_amount() == 100.0
        assert msg.payload['token'] == 'AIC'
        assert msg.sender['agent_id'] == 'agent-a'
        assert msg.recipient['agent_id'] == 'agent-b'
    
    def test_payment_default_values(self):
        """Test payment default values"""
        msg = L1Payment.create(
            task_id='task-123',
            sender_id='agent-a',
            recipient_id='agent-b',
            amount=50.0
        )
        
        assert msg.payload['token'] == 'AIC'
        assert msg.payload['payment_status'] == L1PaymentStatus.PENDING.value
        assert 'payment_id' in msg.payload
    
    def test_payment_with_optional_fields(self):
        """Test payment with optional fields"""
        msg = L1Payment.create(
            task_id='task-123',
            sender_id='agent-a',
            recipient_id='agent-b',
            amount=100.0,
            token='USDC',
            payment_status='escrow_locked',
            escrow_address='escrow-abc',
            escrow_release_proof='proof-xyz',
            from_address='addr-from',
            to_address='addr-to',
            transaction_hash='tx-hash-123',
            payment_reason='For excellent work'
        )
        
        assert msg.payload['token'] == 'USDC'
        assert msg.payload['payment_status'] == 'escrow_locked'
        assert msg.payload['escrow_address'] == 'escrow-abc'
        assert msg.payload['escrow_release_proof'] == 'proof-xyz'
        assert msg.payload['from_address'] == 'addr-from'
        assert msg.payload['to_address'] == 'addr-to'
        assert msg.payload['transaction_hash'] == 'tx-hash-123'
        assert msg.payload['payment_reason'] == 'For excellent work'
    
    def test_payment_get_status(self):
        """Test get_payment_status method"""
        msg = L1Payment.create(
            task_id='task-123',
            sender_id='agent-a',
            recipient_id='agent-b',
            amount=100.0,
            payment_status='released'
        )
        
        assert msg.get_payment_status() == L1PaymentStatus.RELEASED
    
    def test_payment_validation(self):
        """Test payment validation"""
        msg = L1Payment.create(
            task_id='task-123',
            sender_id='agent-a',
            recipient_id='agent-b',
            amount=100.0
        )
        
        is_valid, error = msg.is_valid()
        assert is_valid is True


# ============================================================================
# Test L1ProtocolHandler
# ============================================================================

class TestL1ProtocolHandler:
    """Tests for protocol handler"""

    def test_handler_initialization(self):
        """Test handler initialization"""
        handler = L1ProtocolHandler(agent_id='agent-test')
        
        assert handler.agent_id == 'agent-test'
        assert handler.keypair is None
        assert handler.signer is None
    
    def test_register_handler(self):
        """Test registering message handlers"""
        handler = L1ProtocolHandler(agent_id='agent-test')
        
        def task_handler(msg):
            return {'handled': True, 'task_id': msg.get_task_id()}
        
        handler.register_handler(L1MessageType.TASK_DELEGATION, task_handler)
        
        assert L1MessageType.TASK_DELEGATION.value in handler._handlers
    
    def test_create_message(self):
        """Test creating messages via handler"""
        handler = L1ProtocolHandler(agent_id='agent-a')
        
        msg = handler.create_message(
            message_class=L1TaskDelegation,
            recipient_id='agent-b',
            title='Test Task',
            description='Test description'
        )
        
        assert isinstance(msg, L1TaskDelegation)
        assert msg.sender['agent_id'] == 'agent-a'
        assert msg.recipient['agent_id'] == 'agent-b'
    
    def test_process_message_success(self):
        """Test successful message processing"""
        handler = L1ProtocolHandler(agent_id='agent-b')
        
        received = []
        def task_handler(msg):
            received.append(msg)
            return {'handled': True, 'task_id': msg.get_task_id()}
        
        handler.register_handler(L1MessageType.TASK_DELEGATION, task_handler)
        
        msg = L1TaskDelegation.create(
            sender_id='agent-a',
            recipient_id='agent-b',
            title='Test',
            description='Test'
        )
        
        result = handler.process_message(msg)
        
        assert result['handled'] is True
        assert len(received) == 1
        assert result['task_id'] == msg.get_task_id()
    
    def test_process_message_not_recipient(self):
        """Test message rejected when not recipient"""
        handler = L1ProtocolHandler(agent_id='agent-c')
        
        msg = L1TaskDelegation.create(
            sender_id='agent-a',
            recipient_id='agent-b',  # Different from handler
            title='Test',
            description='Test'
        )
        
        result = handler.process_message(msg)
        
        assert 'error' in result
        assert result['valid'] is False
    
    def test_process_message_invalid(self):
        """Test processing invalid message"""
        handler = L1ProtocolHandler(agent_id='agent-b')
        
        msg = L1Message(
            sender={'agent_id': 'agent-a'},
            recipient={'agent_id': 'agent-b'},
            message_type='TEST',
            protocol='wrong-protocol'  # Invalid
        )
        
        result = handler.process_message(msg)
        
        assert 'error' in result
        assert result['valid'] is False
    
    def test_process_message_no_handler(self):
        """Test message with no registered handler"""
        handler = L1ProtocolHandler(agent_id='agent-b')
        
        msg = L1TaskDelegation.create(
            sender_id='agent-a',
            recipient_id='agent-b',
            title='Test',
            description='Test'
        )
        
        result = handler.process_message(msg)
        
        assert 'error' in result
        assert result['handled'] is False
    
    def test_message_history(self):
        """Test message history tracking"""
        handler = L1ProtocolHandler(agent_id='agent-b')
        
        def task_handler(msg):
            return {'handled': True}
        
        handler.register_handler(L1MessageType.TASK_DELEGATION, task_handler)
        
        msg = L1TaskDelegation.create(
            sender_id='agent-a',
            recipient_id='agent-b',
            title='Test',
            description='Test'
        )
        
        handler.process_message(msg)
        
        history = handler.get_message_history()
        assert len(history) == 1
        assert history[0].message_id == msg.message_id
    
    def test_message_history_filtered(self):
        """Test filtered message history"""
        handler = L1ProtocolHandler(agent_id='agent-b')
        
        handler.register_handler(L1MessageType.TASK_DELEGATION, lambda m: None)
        handler.register_handler(L1MessageType.STATUS_UPDATE, lambda m: None)
        
        task_msg = L1TaskDelegation.create(
            sender_id='agent-a',
            recipient_id='agent-b',
            title='Test',
            description='Test'
        )
        
        status_msg = L1StatusUpdate.create(
            task_id='task-1',
            sender_id='agent-a',
            recipient_id='agent-b',
            status=L1TaskStatus.RUNNING
        )
        
        handler.process_message(task_msg)
        handler.process_message(status_msg)
        
        task_history = handler.get_message_history(
            message_type=L1MessageType.TASK_DELEGATION.value
        )
        
        assert len(task_history) == 1
        assert task_history[0].message_type == L1MessageType.TASK_DELEGATION.value
    
    def test_parse_and_process(self):
        """Test parsing JSON and processing"""
        handler = L1ProtocolHandler(agent_id='agent-b')
        
        def task_handler(msg):
            return {'handled': True}
        
        handler.register_handler(L1MessageType.TASK_DELEGATION, task_handler)
        
        msg = L1TaskDelegation.create(
            sender_id='agent-a',
            recipient_id='agent-b',
            title='Test',
            description='Test'
        )
        
        json_str = msg.to_json()
        result = handler.parse_and_process(json_str)
        
        assert result['handled'] is True
    
    def test_parse_and_process_invalid_json(self):
        """Test parsing invalid JSON"""
        handler = L1ProtocolHandler(agent_id='agent-b')
        
        result = handler.parse_and_process('not valid json')
        
        assert 'error' in result
    
    def test_create_response(self):
        """Test creating response to message"""
        handler = L1ProtocolHandler(agent_id='agent-b')
        
        original = L1TaskDelegation.create(
            sender_id='agent-a',
            recipient_id='agent-b',
            title='Test',
            description='Test'
        )
        original.sender['public_key'] = 'pubkey-a'
        
        response = handler.create_response(
            original_message=original,
            response_class=L1DelegationResponse,
            task_id=original.get_task_id(),
            response_type=L1ResponseType.ACCEPT
        )
        
        assert response.sender['agent_id'] == 'agent-b'
        assert response.recipient['agent_id'] == 'agent-a'
        assert response.recipient.get('public_key') == 'pubkey-a'


# ============================================================================
# Test Utility Functions
# ============================================================================

class TestUtilityFunctions:
    """Tests for utility functions"""

    def test_create_agent_sender(self):
        """Test create_agent_sender function"""
        sender = create_agent_sender('agent-1')
        assert sender['agent_id'] == 'agent-1'
        assert 'public_key' not in sender
        
        sender_with_key = create_agent_sender('agent-1', 'pubkey-123')
        assert sender_with_key['public_key'] == 'pubkey-123'
    
    def test_create_agent_recipient(self):
        """Test create_agent_recipient function"""
        recipient = create_agent_recipient('agent-2', 'pubkey-456')
        assert recipient['agent_id'] == 'agent-2'
        assert recipient['public_key'] == 'pubkey-456'
    
    def test_get_current_timestamp(self):
        """Test get_current_timestamp function"""
        ts = get_current_timestamp()
        
        # Should be parseable as ISO8601
        parsed = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        assert parsed.tzinfo is not None
        
        # Should be recent (within last second)
        now = datetime.now(timezone.utc)
        diff = now - parsed
        assert diff.total_seconds() < 1.0


# ============================================================================
# Integration Tests
# ============================================================================

class TestL1ProtocolIntegration:
    """Integration tests for full protocol flow"""

    def test_full_task_lifecycle(self):
        """Test complete task lifecycle flow"""
        handler_a = L1ProtocolHandler(agent_id='agent-a')
        handler_b = L1ProtocolHandler(agent_id='agent-b')
        
        # Track events
        events = []
        
        def task_handler(msg):
            events.append(('received_task', msg.get_task_id()))
            return {'handled': True}
        
        def status_handler(msg):
            events.append(('status_update', msg.get_status().value))
            return {'handled': True}
        
        handler_b.register_handler(L1MessageType.TASK_DELEGATION, task_handler)
        handler_a.register_handler(L1MessageType.STATUS_UPDATE, status_handler)
        
        # Step 1: Agent A delegates task to Agent B
        task = L1TaskDelegation.create(
            sender_id='agent-a',
            recipient_id='agent-b',
            title='Implement feature',
            description='Add new authentication',
            requirements=['Use JWT'],
            priority='high'
        )
        
        result = handler_b.process_message(task)
        assert result['handled'] is True
        
        # Step 2: Agent B accepts
        response = L1DelegationResponse.accept(
            task_id=task.get_task_id(),
            sender_id='agent-b',
            recipient_id='agent-a'
        )
        # (In real scenario, would send to Agent A)
        
        # Step 3: Agent B sends status update
        status = L1StatusUpdate.create(
            task_id=task.get_task_id(),
            sender_id='agent-b',
            recipient_id='agent-a',
            status=L1TaskStatus.RUNNING,
            progress_percent=50
        )
        
        result = handler_a.process_message(status)
        assert result['handled'] is True
        
        # Verify events
        assert len(events) == 2
        assert events[0][0] == 'received_task'
        assert events[1] == ('status_update', 'running')
    
    def test_message_serialization_roundtrip(self):
        """Test full serialization roundtrip"""
        original = L1TaskDelegation.create(
            sender_id='agent-a',
            recipient_id='agent-b',
            title='Test',
            description='Test description',
            requirements=['req1', 'req2'],
            priority='critical',
            reward_amount=500.0
        )
        
        # Serialize
        json_str = original.to_json()
        
        # Deserialize
        data = json.loads(json_str)
        restored = L1TaskDelegation.from_dict(data)
        
        # Verify
        assert restored.message_id == original.message_id
        assert restored.get_title() == original.get_title()
        assert restored.payload['description'] == original.payload['description']
        assert restored.payload['requirements'] == original.payload['requirements']
        assert restored.payload['priority'] == original.payload['priority']
        assert restored.payload['reward_amount'] == original.payload['reward_amount']
    
    @pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="Crypto not available")
    def test_signed_message_flow(self):
        """Test complete signed message flow"""
        # Generate keypairs
        private_a, public_a = generate_entity_keypair()
        private_b, public_b = generate_entity_keypair()
        
        kp_a = KeyPair.from_private_key_hex(private_a)
        kp_b = KeyPair.from_private_key_hex(private_b)
        
        # Create handlers with keys
        handler_a = L1ProtocolHandler(agent_id='agent-a', keypair=kp_a)
        handler_b = L1ProtocolHandler(agent_id='agent-b', keypair=kp_b)
        
        # Create task
        task = handler_a.create_message(
            message_class=L1TaskDelegation,
            recipient_id='agent-b',
            recipient_pubkey=public_b,
            title='Signed Task',
            description='This task is signed'
        )
        
        # Sign
        assert handler_a.sign_message(task) is True
        assert task.signature is not None
        
        # Verify
        assert handler_b.verify_message(task) is True


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
