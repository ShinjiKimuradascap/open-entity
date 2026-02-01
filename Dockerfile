FROM python:3.11-slim

# システム依存関係
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    build-essential \
    libmagic1 \
    # Playwright/Chromium dependencies
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js and Playwright
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g agent-browser playwright \
    && npx playwright install chromium \
    && rm -rf /var/lib/apt/lists/*

# 非rootユーザーを作成
RUN useradd -m -s /bin/bash moco

# 作業ディレクトリ
WORKDIR /app

# ソースをコピー
COPY pyproject.toml README.md ./
COPY src/ ./src/

# パッケージをインストール
RUN pip install --no-cache-dir -e .

# プロファイルディレクトリを作成
RUN mkdir -p /app/profiles /app/data /home/moco/workspace && \
    chown -R moco:moco /app /home/moco

# 環境変数
ENV PYTHONUNBUFFERED=1
ENV MOCO_HOME=/app
ENV MOCO_DATA_DIR=/app/data

# 非rootユーザーに切り替え
USER moco

# ポート
EXPOSE 8000

# デフォルトコマンド（--reload でホットリロード有効）
CMD ["open-entity", "ui", "--host", "0.0.0.0", "--reload"]
