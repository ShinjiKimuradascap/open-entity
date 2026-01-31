# ============================================
# Multi-stage build for optimized image size
# ============================================

# ----------------------------------------
# Stage 1: Builder
# ----------------------------------------
FROM python:3.11-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Upgrade pip
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ----------------------------------------
# Stage 2: Runtime
# ----------------------------------------
FROM python:3.11-slim AS runtime

# Security labels
LABEL maintainer="AI Collaboration Platform Team" \
      description="AI Peer Communication Platform API Server" \
      version="1.0.0" \
      security.scan="enabled"

# Install runtime dependencies only (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -s /bin/false appuser

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy application code
COPY --chown=appuser:appuser setup.py .
COPY --chown=appuser:appuser README.md .
COPY --chown=appuser:appuser services/ ./services/
COPY --chown=appuser:appuser protocol/ ./protocol/
COPY --chown=appuser:appuser config/ ./config/

# Environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV ENTITY_PRIVATE_KEY=""

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Set working directory for service
WORKDIR /app/services

# Default command
CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8000"]
