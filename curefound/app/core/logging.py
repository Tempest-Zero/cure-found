"""structlog + stdlib logging + asgi-correlation-id setup.

Called once from `create_app()`. Produces:
  - structured JSON logs in non-local environments (parsable by Grafana,
    Cloudwatch, whatever we ship with eventually);
  - pretty console logs in local dev (easier to read during FYP demos);
  - a `request_id` key on every log line that comes from inside a request
    handler, populated by asgi-correlation-id middleware.

Keep this thin. Sentry / Loki / OpenTelemetry can wrap around it in
Phase 6 without touching the per-log-line code.
"""

from __future__ import annotations

import logging
import sys

import structlog
from asgi_correlation_id.context import correlation_id


def _correlation_id_processor(_logger, _method, event_dict):
    """Inject the current correlation id into every structlog record.

    asgi-correlation-id stores the id in a contextvar; if we're not
    inside a request the contextvar is empty and the field is omitted.
    """
    cid = correlation_id.get()
    if cid:
        event_dict["request_id"] = cid
    return event_dict


def configure_logging(level: str = "INFO", *, environment: str = "local") -> None:
    """Initialise structlog + route stdlib loggers through it.

    Idempotent: safe to call multiple times (tests often reconfigure).
    """
    # Map string -> numeric level once.
    numeric_level = logging.getLevelName(level.upper())
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO

    # -------------------- stdlib logging -------------------- #
    # Clear pre-existing handlers so we don't double-print when tests
    # reconfigure.
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    root.setLevel(numeric_level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(numeric_level)
    root.addHandler(handler)

    # Silence chatty third-party loggers a bit.
    for noisy in ("asyncio", "urllib3", "httpx", "neo4j.notifications"):
        logging.getLogger(noisy).setLevel(max(numeric_level, logging.WARNING))

    # -------------------- structlog -------------------- #
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        _correlation_id_processor,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]

    if environment == "local":
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer(
            colors=True,
            exception_formatter=structlog.dev.plain_traceback,
        )
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Convenience wrapper so callers don't import structlog directly."""
    return structlog.get_logger(name) if name else structlog.get_logger()
