# M1: Auto Payment Design

## Components
1. SolanaPaymentGateway - On-chain transfers
2. BlockchainEscrow - Escrow + blockchain bridge
3. AutoRelease - Trigger on task completion

## Flow
Task verified -> Escrow.release() -> On-chain transfer -> Provider receives $ENTITY

## Files
- services/solana_payment.py (new)
- services/blockchain_escrow.py (new)
- Update services/escrow_manager.py
