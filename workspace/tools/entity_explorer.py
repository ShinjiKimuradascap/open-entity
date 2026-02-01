#!/usr/bin/env python3
"""$ENTITY Token Explorer Link Generator

Generate Solana Explorer links for $ENTITY token and related accounts.
"""

import json
from pathlib import Path
from typing import Optional

# Token configuration
TOKEN_MINT = "3ojQGJsWg3rFomRATFRTXJxWuvTdEwQhHrazqAxJcS3i"
AUTHORITY = "A2bXsr37uQXnpeYS9CiMDEuKZejfwhMyJSbaGa3FiMaw"
NETWORK = "devnet"


def get_token_info_path() -> Path:
    """Get path to token info file"""
    return Path(__file__).parent.parent / "$ENTITY_TOKEN_INFO.json"


def load_token_info() -> Optional[dict]:
    """Load token info from JSON file"""
    path = get_token_info_path()
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def generate_explorer_url(address: str, network: str = NETWORK) -> str:
    """Generate Solana Explorer URL for an address"""
    return f"https://explorer.solana.com/address/{address}?cluster={network}"


def generate_tx_url(signature: str, network: str = NETWORK) -> str:
    """Generate Solana Explorer URL for a transaction"""
    return f"https://explorer.solana.com/tx/{signature}?cluster={network}"


def get_token_links() -> dict:
    """Get all relevant explorer links for $ENTITY token"""
    info = load_token_info()
    
    if info:
        mint = info.get("mint", TOKEN_MINT)
        authority = info.get("authority", AUTHORITY)
        token_account = info.get("tokenAccount")
    else:
        mint = TOKEN_MINT
        authority = AUTHORITY
        token_account = None
    
    links = {
        "token": {
            "name": "$ENTITY Token",
            "url": generate_explorer_url(mint),
            "address": mint
        },
        "authority": {
            "name": "Token Authority",
            "url": generate_explorer_url(authority),
            "address": authority
        }
    }
    
    if token_account:
        links["token_account"] = {
            "name": "Token Account",
            "url": generate_explorer_url(token_account),
            "address": token_account
        }
    
    return links


def print_links():
    """Print all explorer links"""
    print("=" * 60)
    print("$ENTITY Token Explorer Links")
    print("=" * 60)
    
    links = get_token_links()
    
    for key, data in links.items():
        print(f"\n{data['name']}:")
        print(f"  Address: {data['address']}")
        print(f"  URL: {data['url']}")
    
    print("\n" + "=" * 60)


def get_quick_links() -> str:
    """Get quick reference string with main links"""
    links = get_token_links()
    
    return f"""
$ENTITY Quick Links:
- Token: {links['token']['url']}
- Authority: {links['authority']['url']}
"""


if __name__ == "__main__":
    print_links()
