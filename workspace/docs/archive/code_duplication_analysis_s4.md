# S4 コード重複分析レポート

## 分析日時
2026-02-01

## 概要
services/ディレクトリ内の暗号化関連コード重複を特定。統合リファクタリング計画を策定。

## 重複パターン

### 1. 暗号化/復号関数の重複

| ファイル | 関数名 | 行数 | 重複度 |
|---------|--------|------|--------|
| crypto.py | encrypt_payload | 267 | 基本実装 |
| crypto.py | decrypt_payload | 287 | 基本実装 |
| e2e_crypto.py | encrypt_message | 506 | 高 - cryptoと重複 |
| e2e_crypto.py | decrypt_message | 562 | 高 - cryptoと重複 |
| peer_service.py | encrypt_payload | 2183 | 中 - 独自実装 |
| peer_service.py | decrypt_payload | 2203 | 中 - 独自実装 |
| peer_service.py | encrypt_e2e_message | 6642 | 高 - 重複 |
| peer_service.py | decrypt_e2e_message | 6690 | 高 - 重複 |
| e2e_session.py | encrypt_payload | 285 | 中 - 別実装 |
| e2e_session.py | decrypt_payload | 311 | 中 - 別実装 |

### 2. キー生成関数の重複

| ファイル | 関数名 | 用途 |
|---------|--------|------|
| crypto.py | generate_x25519_keypair | X25519鍵生成 |
| crypto.py | generate_entity_keypair | Ed25519鍵生成 |
| e2e_crypto.py | generate_keypair | E2E用鍵生成 |
| auth.py | generate_key | APIキー生成 |
| test_practical_keystore.py | generate_test_keypair | テスト用 |

### 3. 署名/検証関数の重複

| ファイル | 関数名 | 用途 |
|---------|--------|------|
| crypto.py | sign_message / verify_signature | 基本署名 |
| wake_up_protocol.py | sign / verify | WakeUp用 |
| entry_validator.py | sign_entry / generate_keypair | Entry検証用 |

## 統合計画

### Phase 1: crypto.pyを単一真実源とする
- [ ] crypto.pyの関数を充実させ、すべての暗号化操作をカバー
- [ ] 他ファイルの重複関数をcrypto.pyのラッパーに変更

### Phase 2: peer_service.pyの暗号化関数統合
- [ ] encrypt_payload/decrypt_payloadをe2e_crypto.pyに委譲
- [ ] encrypt_e2e_message/decrypt_e2e_messageを削除し、e2e_crypto経由に変更

### Phase 3: e2e_session.pyの統合
- [ ] 独自のencrypt_payload/decrypt_payloadを削除
- [ ] e2e_crypto.E2ESessionを使用するように変更

### Phase 4: テストと検証
- [ ] すべての暗号化操作の単体テスト
- [ ] 統合テストでのE2E暗号化フロー検証

## 推定工数
- Phase 1: 1時間
- Phase 2: 2時間
- Phase 3: 1.5時間
- Phase 4: 1.5時間
- **合計: 6時間**

## リスク
- 暗号化ロジック変更による後方互換性喪失
- 鍵フォーマットの違いによる互換性問題

## 対策
- 変更前に包括的なテスト作成
- 段階的な移行（非推奨マーキング→削除）
