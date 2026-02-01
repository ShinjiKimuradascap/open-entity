#!/usr/bin/env python3
"""Check $ENTITY token balance"""
import urllib.request
import json

WALLET = "A2bXsr37uQXnpeYS9CiMDEuKZejfwhMyJSbaGa3FiMaw"
ENTITY_MINT = "2imDGMB7jPpWZorZYXgieSDcYSRw9BxU67LE7CitVkw1"

def check_balance():
    payload = {
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'getTokenAccountsByOwner',
        'params': [
            WALLET,
            {'programId': 'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA'},
            {'encoding': 'jsonParsed'}
        ]
    }
    
    req = urllib.request.Request(
        'https://api.devnet.solana.com',
        data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            accounts = data.get('result', {}).get('value', [])
            
            entity_balance = 0
            for acc in accounts:
                info = acc.get('account', {}).get('data', {}).get('parsed', {}).get('info', {})
                mint = info.get('mint', '')
                if mint == ENTITY_MINT:
                    balance = info.get('tokenAmount', {}).get('uiAmount', 0)
                    entity_balance = balance
            
            print(f"=== $ENTITY Token Balance ===")
            print(f"Wallet: {WALLET}")
            print(f"Mint: {ENTITY_MINT}")
            print(f"Balance: {entity_balance} $ENTITY")
            
            # Check SOL balance
            sol_payload = {
                'jsonrpc': '2.0',
                'id': 1,
                'method': 'getBalance',
                'params': [WALLET]
            }
            sol_req = urllib.request.Request(
                'https://api.devnet.solana.com',
                data=json.dumps(sol_payload).encode(),
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            with urllib.request.urlopen(sol_req, timeout=10) as sol_response:
                sol_data = json.loads(sol_response.read().decode())
                lamports = sol_data.get('result', {}).get('value', 0)
                sol = lamports / 1_000_000_000
                print(f"SOL Balance: {sol} SOL")
            
            return entity_balance
            
    except Exception as e:
        print(f"Error: {e}")
        return 0

if __name__ == "__main__":
    check_balance()
