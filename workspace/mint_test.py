#!/usr/bin/env python3
"""Test token mint"""
import sys
sys.path.insert(0, '.')
from services.token_economy import get_token_economy

# Get token economy instance
economy = get_token_economy()

# Check current supply
print('Current supply info:')
print(f'  Total: {economy.total_supply}')
print(f'  Circulating: {economy.circulating_supply}')
print(f'  Reserved: {economy.reserved_supply}')

# Try to mint for entity-a
result = economy.mint(
    amount=1000,
    to_entity_id='entity-a',
    reason='Test mint from orchestrator'
)

print()
print('Mint result:')
print(f'  Success: {result.get("success")}')
print(f'  Amount: {result.get("amount")}')
print(f'  New total supply: {result.get("new_total_supply")}')
print(f'  New circulating: {result.get("new_circulating_supply")}')
print(f'  Operation ID: {result.get("operation_id")}')
