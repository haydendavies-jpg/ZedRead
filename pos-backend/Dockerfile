# ── Build stage ───────────────────────────────────────────────────────────────
# Pinned to the bookworm variant (not the floating "slim" tag) — Docker Hub
# rolled the untagged python:3.12-slim image forward to Debian trixie, whose
# apt repo renamed/split libgdk-pixbuf2.0-0 (see runtime stage below) and broke
# Railway builds with no change on our side. Pin both stages so the base OS
# only moves when we deliberately bump it.
FROM python:3.12-slim-bookworm AS builder

WORKDIR /app

# Install build dependencies (needed for asyncpg, argon2-cffi compilation)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app

# Runtime-only system libraries.
# libpango/libcairo/libgdk-pixbuf/libffi/shared-mime-info are weasyprint's
# runtime dependencies (Stage 21 PDF export, app/services/invoice_pdf_service.py) —
# without them `import weasyprint` (pulled in transitively by main.py) crashes
# the process on startup, so the container never answers /health. Mirrors the
# system libraries .github/workflows/ci.yml already installs for the test suite.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
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

CMD ["sh", "scripts/start.sh"]
