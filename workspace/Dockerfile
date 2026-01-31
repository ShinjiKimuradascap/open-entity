FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy package files
COPY setup.py .
COPY README.md .
COPY services/ ./services/
COPY protocol/ ./protocol/
COPY config/ ./config/

# 環境変数
ENV PYTHONPATH=/app
ENV ENTITY_PRIVATE_KEY=""

WORKDIR /app/services

# デフォルトコマンド (API Serverを起動)
CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8000"]
