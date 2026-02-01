# $ENTITY Token Wallets

## Solana Devnet Wallets

Created: 2026-02-01

### Entity A
- **Public Key**: `4KqtZYL4YgweVg6xtwPnaWdzj51YaptRrigrXe4EPMfJ`
- **Wallet File**: `data/solana_wallets/entity_a_main.json`
- **Explorer**: https://explorer.solana.com/address/4KqtZYL4YgweVg6xtwPnaWdzj51YaptRrigrXe4EPMfJ?cluster=devnet

### Entity B
- **Public Key**: `B399QMKxawQDoqJKRaaEh74pwwmTbuNe5Tx1FBwCKjG9`
- **Wallet File**: `data/solana_wallets/entity_b_main.json`
- **Explorer**: https://explorer.solana.com/address/B399QMKxawQDoqJKRaaEh74pwwmTbuNe5Tx1FBwCKjG9?cluster=devnet

## $ENTITY Token

- **Mint Address**: `2imDGMB7jPpWZorZYXgieSDcYSRw9BxU67LE7CitVkw1`
- **Network**: Solana Devnet
- **Decimals**: 9

## Treasury Wallet

- **Address**: `A2bXsr37uQXnpeYS9CiMDEuKZejfwhMyJSbaGa3FiMaw`
- **Explorer**: https://explorer.solana.com/address/A2bXsr37uQXnpeYS9CiMDEuKZejfwhMyJSbaGa3FiMaw

## Transaction History

### 2026-02-01 - First On-Chain Settlement ✅

| From | To | Amount | TX Signature |
|------|-----|--------|--------------|
| Treasury | Entity A | 0.5 SOL | `3bodS9mz7eVrzzz7xnQj1zMP5Veg6PUW4CABTFZXQA3bTdjK5hPBuvdfq7e4ViFXViNRigDqomdx24gobM6EqkoU` |
| Treasury | Entity B | 0.5 SOL | `5nLSvKU6xRMdA6pRXJhJpymZANns1FFszLm7wFHZ8XQDZ7Py9rVgsU6ukXjZjhZDySZjV6eu6LyR9tZsV6ZKBKt9` |
| Treasury | Entity A | 500 $ENTITY | `5ui7NKM6HY5CLDvVsAeQjjC8NMe7TkPF4614wyNgNCawVUeBKSgMcVokBYVSAvUXs9PfBbVuv1AHPk6gijThxdtF` |
| Treasury | Entity B | 500 $ENTITY | `2YU6wTtYrWutgjWRWfEyndD7QQ6fTZDzC2F5PaiUwBb7S4KocXnGiKCiPRq4X5LrK9DECLepEpcSfjG9eWJhybCV` |
| **Entity A** | **Entity B** | **20 $ENTITY** | Marketplace Order Payment (on-chain) |

### Current Balances

| Entity | SOL | $ENTITY |
|--------|-----|---------|
| Entity A | ~0.5 | 480 |
| Entity B | ~0.5 | 520 |
| Treasury | ~1.98 | 999,999,000 |

## Completed Milestones

- [x] Airdrop SOL to Entity A and B wallets
- [x] Create Associated Token Accounts for $ENTITY
- [x] Transfer $ENTITY tokens from Treasury to Entity wallets
- [x] **Test marketplace transactions with on-chain settlement** ✅
