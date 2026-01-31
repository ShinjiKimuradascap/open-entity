#!/usr/bin/env python3
"""Governanceモジュール簡易動作確認テスト"""
import sys
sys.path.insert(0, 'services')

from decimal import Decimal
from datetime import timedelta
from governance import (
    GovernanceEngine,
    ProposalStatus,
    ProposalType,
    Action,
    GovernanceConfig
)

print("=== Governance Module Integration Test ===")

# Test 1: GovernanceEngine initialization
print("\n1. Testing GovernanceEngine initialization...")
config = GovernanceConfig(
    MIN_TOKENS_TO_PROPOSE=Decimal("100"),
    MIN_TOKENS_TO_VOTE=Decimal("10"),
    VOTING_PERIOD=timedelta(seconds=5),
    DISCUSSION_PERIOD=timedelta(seconds=2),
    EXECUTION_TIMELOCK_SECONDS=1,
    QUORUM_PERCENTAGE=20,
    PASS_THRESHOLD_PERCENTAGE=50
)

engine = GovernanceEngine(config)
balances = {
    "proposer": Decimal("1000"),
    "voter1": Decimal("500"),
    "voter2": Decimal("300"),
}
engine.set_balance_lookup(lambda addr: balances.get(addr, Decimal("0")))
print("✓ GovernanceEngine initialized")

# Test 2: Proposal creation
print("\n2. Testing proposal creation...")
action = Action(
    target="token_contract",
    function="mint",
    parameters={"amount": "1000"}
)

proposal = engine.create_proposal(
    proposer="proposer",
    title="Test Proposal",
    description="A test proposal",
    proposal_type=ProposalType.PARAMETER_CHANGE,
    actions=[action]
)
print(f"✓ Proposal created: {proposal.id}")
print(f"  Title: {proposal.title}")
print(f"  Status: {proposal.status}")

# Test 3: Voting
print("\n3. Testing voting...")
result = engine.vote("voter1", proposal.id, True)
print(f"✓ Vote cast: {result}")

result = engine.vote("voter2", proposal.id, True)
print(f"✓ Vote cast: {result}")

# Test 4: Proposal state
print("\n4. Checking proposal state...")
proposal_state = engine.get_proposal(proposal.id)
print(f"✓ Proposal status: {proposal_state.status}")
print(f"  Total votes for: {proposal_state.votes_for}")
print(f"  Total votes against: {proposal_state.votes_against}")

print("\n=== Governance Module Integration Test Passed ===")
