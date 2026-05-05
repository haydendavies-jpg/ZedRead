"""FastAPI application entry point — app factory, middleware, router registration."""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.database import engine
from app.logging_config import configure_logging
from app.middleware.logging import RequestLoggingMiddleware
from app.routes import brands, combos, groups, license_invoices, licenses, modifiers, portal_auth, portal_users, pos_auth, pos_devices, products, site_overrides, sites, tax, user_invites, variants

# Configure structlog before the app starts accepting requests
configure_logging()

log = structlog.get_logger(__name__)


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

# Attach request ID middleware first (innermost — runs after CORS)
app.add_middleware(RequestLoggingMiddleware)

# CORS must be outermost — added last so it processes requests first.
# Handles preflight OPTIONS before any other middleware sees the request.
# PORTAL_ORIGIN env var set in Railway; falls back to localhost for dev.
_portal_origin = os.getenv("PORTAL_ORIGIN", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_portal_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(portal_auth.router)
app.include_router(pos_auth.router)
app.include_router(groups.router)
app.include_router(brands.router)
app.include_router(sites.router)
app.include_router(portal_users.router)
app.include_router(licenses.router)
app.include_router(license_invoices.router)
app.include_router(pos_devices.router)
app.include_router(user_invites.router)
app.include_router(tax.router)
app.include_router(products.router)
app.include_router(site_overrides.router)
app.include_router(variants.router)
app.include_router(modifiers.router)
app.include_router(combos.router)


# ── Global exception handler ──────────────────────────────────────────────────


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all handler for unhandled exceptions.

    Logs at ERROR level (rule 14) and returns a generic 500 response.
    Prevents raw exception tracebacks from leaking to API consumers.

    Args:
        request: The incoming request.
        exc: The unhandled exception.

    Returns:
        JSONResponse: 500 with a generic error message.
    """
    log.error(
        "unhandled_exception",
        exc_type=type(exc).__name__,
        exc=str(exc),
        path=request.url.path,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


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
