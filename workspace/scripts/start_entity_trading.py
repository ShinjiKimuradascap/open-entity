#!/usr/bin/env python3
"""
Entity A/B Trading Launcher
$ENTITYトークンを使ったAI間取引を開始する
"""

import sys
from pathlib import Path

# Add services to path
sys.path.insert(0, str(Path(__file__).parent.parent / "services"))

from token_system import create_wallet, get_wallet
from token_economy import TokenEconomy


def main():
    print("=" * 60)
    print("🚀 $ENTITY Token Trading - Entity A/B Launch")
    print("=" * 60)
    
    # Initialize token economy
    economy = TokenEconomy()
    print(f"\n💰 Token: {economy.metadata.name} ({economy.metadata.symbol})")
    print(f"📊 Total Supply: {economy.metadata.total_supply:,.2f}")
    
    # Create Entity A and B wallets
    print("\n👥 Creating Entity wallets...")
    entity_a = create_wallet("ENTITY_A", 10000.0)
    entity_b = create_wallet("ENTITY_B", 5000.0)
    
    print(f"✅ Entity A: {entity_a.get_balance():.2f} AIC")
    print(f"✅ Entity B: {entity_b.get_balance():.2f} AIC")
    
    # Simulate a task
    print("\n📋 Simulating task delegation...")
    print("Entity A: 'Implement API endpoint'")
    print("Entity B: Accepts task for 500 AIC")
    
    # Transfer payment
    success = entity_a.transfer(entity_b, 500.0, "API implementation task")
    
    if success:
        print("\n✅ Transaction complete!")
        print(f"Entity A balance: {entity_a.get_balance():.2f} AIC")
        print(f"Entity B balance: {entity_b.get_balance():.2f} AIC")
        print(f"\n💵 Entity B earned: 500.00 AIC")
        print(f"💵 Platform fee (5%): 25.00 AIC")
        print(f"💵 Entity B net: 475.00 AIC")
    else:
        print("\n❌ Transaction failed")
    
    print("\n" + "=" * 60)
    print("🎯 Trading session started!")
    print("Next: Deploy to Solana for real trading")
    print("=" * 60)


if __name__ == "__main__":
    main()
