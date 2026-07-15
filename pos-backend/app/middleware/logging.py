"""Request logging middleware — attaches a UUID request_id to every request."""

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

log = structlog.get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that generates a unique request_id for every incoming request.

    The request_id is:
    - Bound into the structlog context so all log lines within the request
      carry the same ID, enabling full request tracing.
    - Returned in the X-Request-ID response header so clients and load
      balancers can correlate logs with specific requests.
    """

    def __init__(self, app: ASGIApp) -> None:
        """
        Initialise the middleware.

        Args:
            app: The ASGI application to wrap.
        """
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Process a single request: bind request_id, call the route, attach header.

        Args:
            request: The incoming HTTP request.
            call_next: Callable that invokes the next middleware or route handler.

        Returns:
            Response: The HTTP response with X-Request-ID header attached.
        """
        # Generate a new UUID for this request — use hex string to keep it compact
        request_id: str = str(uuid.uuid4())

        # Bind to structlog context so every log line in this request carries it
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        # DEBUG, not INFO — request.completed already carries method/path plus
        # status and duration, so a second line per request is pure log volume
        # in production (where the root logger runs at INFO)
        log.debug(
            "request.started",
            method=request.method,
            path=request.url.path,
        )

        # Monotonic clock — immune to wall-clock adjustments mid-request
        started_at: float = time.monotonic()

        response: Response = await call_next(request)

        duration_ms: int = int((time.monotonic() - started_at) * 1000)

        log.info(
            "request.completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

        # Slow requests get their own WARNING so they stand out in production
        # logs — the first place to look when the portal feels sluggish
        if duration_ms >= 1000:
            log.warning(
                "request.slow",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )

        # Attach the request_id to the response so clients can reference it,
        # and the server-side duration so client-observed latency can be split
        # into server time vs network time when diagnosing slowness
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-Ms"] = str(duration_ms)

        return response
