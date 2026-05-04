#!/bin/sh
# Entrypoint for Railway (and any Docker deployment).
# 1. Runs database migrations.
# 2. If BOOTSTRAP_EMAIL/BOOTSTRAP_NAME/BOOTSTRAP_PASSWORD are set, bootstraps
#    the first super_admin (no-op if one already exists).
# 3. Starts the uvicorn server.
set -e

echo "[start] Running database migrations…"
alembic upgrade head

if [ -n "$BOOTSTRAP_EMAIL" ] && [ -n "$BOOTSTRAP_NAME" ] && [ -n "$BOOTSTRAP_PASSWORD" ]; then
  echo "[start] BOOTSTRAP_* vars detected — running non-interactive bootstrap…"
  # Single-command Typer app: the function IS the root command, no subcommand name needed
  # || true so a bootstrap failure never prevents server startup
  python -m app.cli --non-interactive || echo "[start] Bootstrap failed — see error above; server will still start"
fi

echo "[start] Starting uvicorn on port ${PORT:-8000}…"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
