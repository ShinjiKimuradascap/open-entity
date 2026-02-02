# Sandbox Gateway Dockerfile
FROM python:3.11-slim

# 必要なツールのみインストール（gcloud CLI は入れない！）
RUN apt-get update && apt-get install -y \
    procps \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 依存関係をインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# サンドボックスディレクトリを作成
RUN mkdir -p /app/sandbox/services /app/sandbox/data /app/sandbox/logs

# アプリケーションコードをコピー
COPY sandbox_gateway.py .

# ポート設定
ENV PORT=8080
EXPOSE 8080

# 非rootユーザーで実行（セキュリティ強化）
RUN useradd -m -d /app/sandbox sandboxuser \
    && chown -R sandboxuser:sandboxuser /app
USER sandboxuser

# 起動コマンド
CMD ["python", "sandbox_gateway.py"]
