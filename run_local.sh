#!/bin/bash
# Open Entity ローカル実行スクリプト
# Dockerなしで直接Pythonを実行

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "🚀 Open Entity をローカルモードで起動します..."

# 1. workspace フォルダを作成
mkdir -p workspace

# 2. .env ファイルの存在確認
if [ ! -f .env ]; then
    if [ -f ../.env ]; then
        echo "📋 .env をコピーしています..."
        cp ../.env .env
    else
        echo "⚠️  .env ファイルが見つかりません"
        echo "   .env.example をコピーして設定してください"
        exit 1
    fi
fi

# 3. 仮想環境の確認・作成
VENV_DIR=".venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "🔧 仮想環境を作成しています..."
    python3 -m venv "$VENV_DIR"
fi

# 4. 仮想環境を有効化
echo "🔧 仮想環境を有効化しています..."
source "$VENV_DIR/bin/activate"

# 5. 依存関係のインストール（必要に応じて）
if [ ! -f ".deps_installed" ] || [ "pyproject.toml" -nt ".deps_installed" ]; then
    echo "📦 依存関係をインストールしています..."
    pip install -q -e ".[dev]"
    touch .deps_installed
fi

# 6. 環境変数の設定
export MOCO_WORKING_DIRECTORY="${MOCO_WORKING_DIRECTORY:-$SCRIPT_DIR/workspace}"
export MOCO_PROFILE="${MOCO_PROFILE:-entity}"

echo ""
echo "✅ 準備完了！"
echo ""
echo "使い方:"
echo "  oe --version          # バージョン確認"
echo "  oe list-profiles      # プロファイル一覧"
echo "  oe run 'タスク内容'    # タスク実行"
echo "  oe --help            # ヘルプ"
echo ""
echo "💡 現在のプロファイル: $MOCO_PROFILE"
echo "💡 作業ディレクトリ: $MOCO_WORKING_DIRECTORY"
