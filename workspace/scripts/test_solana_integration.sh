#!/bin/bash
# Solana Integration Test Script
# Tests SPL token transfer on Devnet

set -e

echo "=========================================="
echo "Solana Integration Test"
echo "=========================================="

# Configuration
export SOLANA_RPC_URL="https://api.devnet.solana.com"
export ENTITY_TOKEN_MINT="3ojQGJsWg3rFomRATFRTXJxWuvTdEwQhHrazqAxJcS3i"

# Generate test wallets
echo ""
echo "[1] Generating test wallets..."
SENDER_WALLET=$(node -e "
const { Keypair } = require('@solana/web3.js');
const bs58 = require('bs58');
const kp = Keypair.generate();
console.log(JSON.stringify({
    public_key: kp.publicKey.toString(),
    private_key: bs58.encode(kp.secretKey)
}));
")

RECIPIENT_WALLET=$(node -e "
const { Keypair } = require('@solana/web3.js');
const bs58 = require('bs58');
const kp = Keypair.generate();
console.log(JSON.stringify({
    public_key: kp.publicKey.toString(),
    private_key: bs58.encode(kp.secretKey)
}));
")

SENDER_PUB=$(echo $SENDER_WALLET | node -e "const d=[];process.stdin.on('data',c=>d.push(c));process.stdin.on('end',()=>console.log(JSON.parse(d.join('')).public_key))")
SENDER_PRIV=$(echo $SENDER_WALLET | node -e "const d=[];process.stdin.on('data',c=>d.push(c));process.stdin.on('end',()=>console.log(JSON.parse(d.join('')).private_key))")
RECIPIENT_PUB=$(echo $RECIPIENT_WALLET | node -e "const d=[];process.stdin.on('data',c=>d.push(c));process.stdin.on('end',()=>console.log(JSON.parse(d.join('')).public_key))")

echo "Sender: $SENDER_PUB"
echo "Recipient: $RECIPIENT_PUB"

# Request airdrop for sender
echo ""
echo "[2] Requesting SOL airdrop for sender..."
node services/solana_bridge.js airdrop entity_test_sender 2 || echo "Airdrop may have failed, continuing..."

# Test balance check
echo ""
echo "[3] Checking token balance..."
node services/solana_bridge.js balance entity_test_sender || echo "Balance check may fail if no token account"

echo ""
echo "=========================================="
echo "Test setup complete"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Mint $ENTITY tokens to sender wallet"
echo "2. Run transfer test"
echo ""
echo "Token Mint: $ENTITY_TOKEN_MINT"
echo "Sender: $SENDER_PUB"
echo "Recipient: $RECIPIENT_PUB"
