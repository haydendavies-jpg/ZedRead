# ── Build stage ───────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies (needed for asyncpg, argon2-cffi compilation)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# Runtime-only system libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY . .

# Non-root user for security
RUN useradd --no-create-home --shell /bin/false appuser \
    && chown -R appuser:appuser /app
USER appuser

# Uvicorn listens on $PORT (Railway sets this automatically)
ENV PORT=8000
EXPOSE $PORT

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT"]
