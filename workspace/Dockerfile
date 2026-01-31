FROM python:3.11-slim

WORKDIR /app

# 依存関係のインストール
RUN pip install --no-cache-dir \
    aiohttp>=3.8.0 \
    fastapi>=0.100.0 \
    uvicorn>=0.23.0 \
    PyNaCl>=1.5.0 \
    python-dotenv>=1.0.0

# ソースコードをコピー
COPY services/ ./services/
COPY protocol/ ./protocol/

# 環境変数
ENV PYTHONPATH=/app
ENV ENTITY_PRIVATE_KEY=""

WORKDIR /app/services

# デフォルトコマンド
CMD ["python", "-c", "print('AI Peer Communication Service Ready')"]
