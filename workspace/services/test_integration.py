#!/usr/bin/env python3
"""
Token Economy + Persistence Integration Test
"""
import sys
sys.path.insert(0, '.')
from token_economy import get_token_economy, TokenMetadata
from token_persistence import PersistenceManager
from token_system import create_wallet, get_wallet

print('=== Token Economy + Persistence Integration Test ===')

# Initialize
economy = get_token_economy()
pm = PersistenceManager('data/tokens_test')

# Create test wallets
wallets = {
    'alice': create_wallet('alice', 0),
    'bob': create_wallet('bob', 0)
}

# Mint tokens
economy.mint(5000, 'alice', 'Test mint for alice')
economy.mint(3000, 'bob', 'Test mint for bob')

print(f'Total supply: {economy.get_total_supply()}')
print(f'Alice balance: {wallets["alice"].get_balance()}')
print(f'Bob balance: {wallets["bob"].get_balance()}')

# Burn some tokens
economy.burn(500, wallets['alice'], 'Test burn')
print(f'After burn - Alice: {wallets["alice"].get_balance()}, Total: {economy.get_total_supply()}')

# Save wallets
pm.save_wallets(wallets)

# Save economy state
import json
with open('data/tokens_test/economy.json', 'w') as f:
    json.dump(economy.to_dict(), f, indent=2)
print('Economy state saved')

# Load back
with open('data/tokens_test/economy.json', 'r') as f:
    loaded_economy = json.load(f)
print(f'Loaded economy - Total supply: {loaded_economy["metadata"]["total_supply"]}')

print('=== Integration Test Complete ===')
