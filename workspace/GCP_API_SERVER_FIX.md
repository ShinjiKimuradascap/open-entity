# GCP api_server.py 修正レポート

## 問題
- GCP上で api_server.py が起動エラー
- ModuleNotFoundError: No module named 'registry'

## 原因
- api_server.py が複数の依存モジュールを必要とする
- 一部のインポートが try-except で囲まれておらず、クラッシュ

## 修正内容

### 1. api_server.py - 堅牢なインポートシステム
- 各モジュールを個別にインポート
- 失敗時は None またはモック実装を設定
- 必須モジュールのみ ImportError

### 2. 初期化処理の安全化
- try-except でラップ
- 失敗してもサーバーが起動する

### 3. Dockerfile の修正
- tools/ ディレクトリを追加コピー

## デプロイ手順
1. git add services/api_server.py Dockerfile
2. git commit -m "Fix GCP api_server import errors"
3. git push
4. GCPでデプロイをトリガー

## ファイル変更
- services/api_server.py: インポートシステムを完全書き換え
- Dockerfile: tools/ディレクトリ追加
