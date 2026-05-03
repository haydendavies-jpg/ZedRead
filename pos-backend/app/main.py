"""FastAPI application entry point — app factory, middleware, router registration."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.database import engine
from app.logging_config import configure_logging
from app.middleware.logging import RequestLoggingMiddleware

# Configure structlog before the app starts accepting requests
configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan handler.

    Runs a lightweight DB connectivity check on startup so misconfigured
    DATABASE_URL values are caught immediately rather than at first request.

    Args:
        app: The FastAPI application instance.

    Yields:
        None: Control passes to the running application.
    """
    # Verify database is reachable before accepting traffic
    # Skipped in test environments where the engine may point at the dev DB
    import os
    if os.getenv("SKIP_DB_STARTUP_CHECK", "").lower() != "true":
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    yield  # Application runs here

    # Dispose the connection pool cleanly on shutdown
    await engine.dispose()


app = FastAPI(
    title="ZedRead POS API",
    description="Multi-tenant point-of-sale backend.",
    version="0.1.0",
    lifespan=lifespan,
)

# Attach request ID middleware — must be added before any route middleware
app.add_middleware(RequestLoggingMiddleware)


# ── Health check ──────────────────────────────────────────────────────────────


class HealthResponse(JSONResponse):
    """Typed response model for the health check route."""

    pass


@app.get("/health", response_model=dict, tags=["meta"])
async def health_check() -> dict:
    """
    Liveness probe endpoint.

    Returns a simple status payload. The lifespan hook already confirmed
    the database is reachable at startup, so this route is intentionally
    kept lightweight — it does not re-query the DB on every call.

    Returns:
        dict: {"status": "ok"}
    """
    return {"status": "ok"}
