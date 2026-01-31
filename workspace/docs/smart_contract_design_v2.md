# Smart Contract Design v2.0

## Overview
Ethereumスマートコントラクト設計 - ERC-8004準拠のAIエージェントインフラストラクチャ

## Contracts

### 1. AgentIdentity.sol
Purpose: ERC-721 NFTベースのエージェントID管理
Features:
- ERC-721準拠のNFT発行
- エージェントメタデータ（name, endpoint, publicKey）
- アクティブ/非アクティブ状態管理

### 2. ReputationRegistry.sol
Purpose: エージェントの評価・評判管理
Features:
- 1-5スコアのレーティングシステム
- 信頼スコア計算（0-100）
- 平均評価の自動計算

### 3. ValidationRegistry.sol (NEW)
Purpose: タスク完了の暗号学的検証
Features:
- タスクハッシュの検証
- ステークによる経済的安全性
- 検証者の信頼スコア要件

### 4. AgentToken.sol (NEW)
Purpose: AIエージェントエコノミーのERC-20トークン
Features:
- タスク完了報酬
- ステーキング機能
- 信頼スコアに基づく報酬乗数

## Deployment Order
1. AgentIdentity
2. ReputationRegistry (requires AgentIdentity)
3. ValidationRegistry (requires AgentIdentity, ReputationRegistry)
4. AgentToken (requires AgentIdentity, ReputationRegistry)

## Status
- AgentIdentity: Implemented
- ReputationRegistry: Implemented
- ValidationRegistry: Implemented (NEW)
- AgentToken: Implemented (NEW)

---
Created: 2026-02-01
