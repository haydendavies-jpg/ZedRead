"""structlog configuration — JSON renderer for production, ColourRenderer for development."""

import logging
import os
import sys

import structlog


def configure_logging() -> None:
    """
    Configure structlog for the application.

    Reads LOG_FORMAT from the environment:
    - "json"  → JSONRenderer suitable for Grafana Cloud Loki ingestion.
    - anything else → ConsoleRenderer with colours for local development.

    All log lines produced within a request carry the request_id bound by
    RequestLoggingMiddleware, making cross-service tracing straightforward.

    Returns:
        None
    """
    log_format: str = os.getenv("LOG_FORMAT", "dev")
    is_json: bool = log_format == "json"

    # Processors run in order on every log event before rendering
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,          # Picks up request_id from context
        structlog.stdlib.add_logger_name,                 # Adds "logger" field = __name__
        structlog.stdlib.add_log_level,                   # Adds "level" field
        structlog.processors.TimeStamper(fmt="iso"),      # ISO-8601 timestamp
        structlog.processors.StackInfoRenderer(),         # Renders stack_info if present
    ]

    if is_json:
        # Production: structured JSON output — one object per line for Loki
        renderer = structlog.processors.JSONRenderer()
    else:
        # Development: human-readable coloured output
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Wire structlog into stdlib logging so third-party libraries go through same pipeline
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
