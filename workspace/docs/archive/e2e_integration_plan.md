# E2ECryptoManager統合計画

## 現状
- crypto.pyにE2EEncryptionクラス（基本的なX25519/AES-GCM）
- e2e_crypto.pyにE2ECryptoManager（完全なセッション管理）
- peer_service.pyにE2EEncryptionを使用するコード（部分的）

## 統合目標
E2ECryptoManagerを使用して、より堅牢なE2E暗号化を実現

## 統合ステップ

### Phase 1: インポートと初期化
1. peer_service.pyにE2ECryptoManagerをインポート
2. __init__でE2ECryptoManagerを初期化（e2e_encryptionの代わり）
3. 後方互換性のため既存のe2e_encryptionも保持

### Phase 2: セッション管理
1. ピア接続時にE2Eセッションを確立
2. セッションタイムアウトとクリーンアップ
3. セッション状態の監視

### Phase 3: メッセージ暗号化統合
1. send_messageでE2Eセッションを使用
2. receive_messageで復号化
3. フォールバック（セッションがない場合）

### Phase 4: ハンドシェイク統合
1. E2EHandshakeHandlerを統合
2. handshake/e2e_handshakeメッセージタイプを処理

## 実装ファイル
- services/peer_service.py - 統合先
- services/e2e_crypto.py - 統合元（変更なし）

## テスト計画
1. 既存のテストが通ること
2. E2E暗号化の統合テスト
3. パフォーマンステスト
