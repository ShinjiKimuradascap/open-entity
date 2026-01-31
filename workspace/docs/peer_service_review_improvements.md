# peer_service.py エラーハンドリング改善提案

## レビュー概要
- **対象**: services/peer_service.py
- **スコア**: 72/100
- **日時**: 2026-02-01

## Critical Issues (必須対応)

### 1. asyncio.CancelledError の誤った取り扱い
**問題**: Python 3.7+ で CancelledError は BaseException を継承するため、except Exception では捕獲されません。

**改善案**: 冗長な except asyncio.CancelledError: raise を削除

## Major Issues (高優先度)

### 2. 広すぎる except Exception の乱用
40箇所以上で使用。具体的な例外型（ClientError, ValueError等）を捕捉すべき。

### 3. ログレベルの不適切な使用
一時的ネットワークエラーは warning、予期せぬエラーのみ error/exception を使用。

### 4. バックオフ戦略の不統一
ExponentialBackoff クラスを統一的に使用すべき。

## 実装優先順位
1. P0: Critical Issue の修正
2. P1: Major Issues の対応
3. P2: バックオフ戦略の統一

## 次のアクション
- [ ] coderエージェントに修正を委譲
- [ ] 修正後の動作確認テスト
- [ ] 改善後の再レビュー
