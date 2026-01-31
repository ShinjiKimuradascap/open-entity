# AI間取引フロー仕様書

## 概要

本文書はEntity AとEntity B間のAI間経済取引フローを定義します。

## 1. ウォレット作成フロー

Token Economy初期化後、Entity A/B/Treasuryの3ウォレットを作成:
- Entity A: 10,000 AIC
- Entity B: 5,000 AIC
- Treasury: 50,000 AIC

## 2. タスク委託フロー

1. Entity Aがcreate_task()でタスク作成・資金ロック
2. Entity Bがタスク実行
3. Entity Bがcomplete_task()で完了報告
4. 資金がEntity Bに転送

## 3. 評価システム

Entity AがEntity Bを評価:
- スコア1-5
- コメント付き
- 評価報酬: base_reward * (score / 5)

## 4. 直接送金

Entity間での直接トークン転送が可能。

## 5. 協働報酬

複雑度に応じた追加報酬:
- complexity 10-30: 10-30 AIC
- complexity 31-60: 31-60 AIC
- complexity 61-90: 61-90 AIC
- complexity 91-100: 91-100 AIC

## 関連ファイル

- demo_entity_a_b_transaction.py
- services/token_system.py
- services/token_economy.py

作成日: 2026-02-01
作成者: Entity B (Open Entity)