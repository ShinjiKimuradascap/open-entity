# Bootstrap Server Dockerfile
FROM python:3.11-slim

WORKDIR /app

# 依存関係
RUN pip install --no-cache-dir fastapi uvicorn aiohttp

# コードをコピー
COPY bootstrap_server.py .

# ポート設定
ENV PORT=8080
EXPOSE 8080

# 非rootユーザー
RUN useradd -m appuser
USER appuser

# 起動
CMD ["python", "-c", "import asyncio; from bootstrap_server import BootstrapServer; server = BootstrapServer(port=8080); asyncio.run(server.start())"]
