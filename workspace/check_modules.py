#!/usr/bin/env python3
"""Quick module import check"""
import sys
sys.path.insert(0, 'services')

modules = [
    'moltbook_integration',
    'moltbook_client', 
    'peer_service',
    'crypto',
    'token_system'
]

results = []
for mod in modules:
    try:
        __import__(mod)
        results.append(f'✅ {mod}')
    except Exception as e:
        results.append(f'❌ {mod}: {str(e)[:50]}')

print('\n'.join(results))
print('\n--- Check complete ---')
