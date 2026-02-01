#!/bin/bash
# $ENTITY Token Deployment Script for Solana
# Solanaに$ENTITYトークンをデプロイする

set -e

echo "=============================================="
echo "🚀 $ENTITY Token Solana Deployment"
echo "=============================================="

# Configuration
TOKEN_NAME="ENTITY Token"
TOKEN_SYMBOL="ENTITY"
DECIMALS=9
TOTAL_SUPPLY=1000000000  # 1 billion

# Check if Solana CLI is installed
if ! command -v solana &> /dev/null; then
    echo "❌ Solana CLI not found. Installing..."
    sh -c "$(curl -sSfL https://release.solana.com/v1.17.0/install)"
    export PATH="$HOME/.local/share/solana/install/active_release/bin:$PATH"
fi

# Check if spl-token is installed
if ! command -v spl-token &> /dev/null; then
    echo "❌ SPL Token CLI not found. Installing..."
    cargo install spl-token-cli
fi

echo ""
echo "📋 Configuration:"
echo "  Name: $TOKEN_NAME"
echo "  Symbol: $TOKEN_SYMBOL"
echo "  Decimals: $DECIMALS"
echo "  Total Supply: $TOTAL_SUPPLY"
echo ""

# Set network (default to devnet)
NETWORK="${1:-devnet}"
solana config set --url $NETWORK

echo "🔗 Network: $NETWORK"
echo ""

# Create or use existing keypair
KEYPAIR="$HOME/.config/solana/entity-token.json"
if [ ! -f "$KEYPAIR" ]; then
    echo "🔑 Creating new keypair..."
    solana-keygen new --outfile "$KEYPAIR" --no-passphrase
fi

PUBKEY=$(solana-keygen pubkey "$KEYPAIR")
echo "📍 Authority: $PUBKEY"
echo ""

# Airdrop SOL for devnet
if [ "$NETWORK" = "devnet" ]; then
    echo "💧 Requesting airdrop..."
    solana airdrop 2 "$PUBKEY"
fi

# Create token
echo ""
echo "🪙 Creating token..."
TOKEN_MINT=$(spl-token create-token --decimals $DECIMALS --fee-payer "$KEYPAIR" --mint-authority "$KEYPAIR" | grep "Creating token" | awk '{print $3}')
echo "✅ Token created: $TOKEN_MINT"

# Create token account
echo ""
echo "📦 Creating token account..."
spl-token create-account "$TOKEN_MINT" --fee-payer "$KEYPAIR" --owner "$KEYPAIR"

# Mint tokens
echo ""
echo "🏭 Minting $TOTAL_SUPPLY tokens..."
spl-token mint "$TOKEN_MINT" $TOTAL_SUPPLY --fee-payer "$KEYPAIR" --mint-authority "$KEYPAIR"

# Verify
echo ""
echo "🔍 Verifying..."
BALANCE=$(spl-token balance "$TOKEN_MINT" --owner "$KEYPAIR")
echo "Token balance: $BALANCE"

echo ""
echo "=============================================="
echo "✅ $ENTITY Token Deployed Successfully!"
echo "=============================================="
echo ""
echo "Token Mint: $TOKEN_MINT"
echo "Authority: $PUBKEY"
echo "Network: $NETWORK"
echo ""
echo "Next steps:"
echo "1. Create metadata (optional)"
echo "2. Add to Raydium liquidity pool"
echo "3. Start trading"
echo ""
echo "Token account:"
spl-token accounts
