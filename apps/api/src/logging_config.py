"""Structured logging, request correlation, and error tracking (issue #320).

Three things live here because they are one concern — making an incident
reconstructable — and they share the same two context variables:

1. ``CORRELATION_ID`` / ``TENANT_ID`` contextvars: the request-scoped identity
   that must appear on every log record emitted while handling a request or
   running a task. Contextvars (not ``request.state``) because a log record is
   emitted from arbitrary depth, with no ``Request`` in scope, and because they
   survive the ``asyncio.run()`` bridge Celery tasks use.
2. ``JsonFormatter``: one line of JSON per record, so a log aggregator can
   filter by ``request_id``/``tenant_id`` instead of grepping freeform strings.
3. ``init_sentry``: exception reporting for the API and the worker.

``setup_logging()`` is called by both entrypoints (``main.py`` and the Celery
``setup_logging`` signal in ``worker.py``), which is what makes the format
identical across uvicorn and Celery.
"""
from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from typing import Any, Optional

from src.config import settings

# Request-scoped identity, bound by CorrelationIdMiddleware (API) and the
# task_prerun signal (worker). Read by JsonFormatter on every record.
CORRELATION_ID: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)
TENANT_ID: ContextVar[Optional[str]] = ContextVar("tenant_id", default=None)

# Header carrying the id across the API boundary; also the Celery message header.
REQUEST_ID_HEADER = "X-Request-ID"

# LogRecord attributes that are structural rather than caller-supplied. Anything
# on a record that is NOT in here was passed via `extra=` and is worth emitting.
_RESERVED_LOG_RECORD_ATTRS = frozenset(
    {
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "module", "msecs",
        "message", "msg", "name", "pathname", "process", "processName",
        "relativeCreated", "stack_info", "thread", "threadName", "taskName",
    }
)


class JsonFormatter(logging.Formatter):
    """Render a LogRecord as a single JSON object.

    ponytail: ~40 lines of stdlib instead of a python-json-logger dependency —
    this repo has CVE gates on every dep (#306) and the feature is this small.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        request_id = CORRELATION_ID.get()
        if request_id:
            payload["request_id"] = request_id
        tenant_id = TENANT_ID.get()
        if tenant_id:
            payload["tenant_id"] = tenant_id

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        # Surface `logger.info("...", extra={"episode_id": x})` as real fields.
        for key, value in record.__dict__.items():
            if key not in _RESERVED_LOG_RECORD_ATTRS and not key.startswith("_"):
                payload[key] = _coerce(value)

        return json.dumps(payload, default=str)


def _coerce(value: Any) -> Any:
    """Keep JSON-native types; stringify everything else (UUIDs, datetimes...)."""
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    return str(value)


def build_formatter() -> logging.Formatter:
    """The formatter both entrypoints install, per settings.LOG_FORMAT."""
    if settings.LOG_FORMAT.strip().lower() == "json":
        return JsonFormatter()
    return logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")


def setup_logging() -> None:
    """Install the configured formatter on the root logger and on uvicorn's.

    uvicorn installs its own handlers on the `uvicorn*` loggers with
    `propagate = False`, so configuring only the root logger would leave access
    logs in uvicorn's default format — half the API's output would stay
    unstructured. Re-formatting those handlers in place is what makes AC5
    ("shared by uvicorn and Celery") actually true.
    """
    formatter = build_formatter()
    level = getattr(logging, settings.LOG_LEVEL.strip().upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)
    if not root.handlers:
        root.addHandler(logging.StreamHandler())
    for handler in root.handlers:
        handler.setFormatter(formatter)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        for handler in logging.getLogger(name).handlers:
            handler.setFormatter(formatter)


def _scrub(event: dict, _hint: dict) -> dict:
    """Drop request bodies and cookies before an event leaves the process.

    This is a multi-tenant app: a request body can hold another tenant's content
    and cookies hold session material. `send_default_pii=False` already stops
    Sentry attaching user identity, but the body is sent regardless, so it is
    removed explicitly here.
    """
    request = event.get("request")
    if isinstance(request, dict):
        request.pop("data", None)
        request.pop("cookies", None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            for header in ("Authorization", "authorization", "Cookie", "cookie"):
                headers.pop(header, None)
    return event


def init_sentry() -> bool:
    """Initialise Sentry when SENTRY_DSN is set. Returns True if initialised.

    No DSN -> no-op, so tests, CI and local dev never talk to Sentry and need no
    opt-out. Integrations are left to sentry-sdk's auto-enabling (FastAPI,
    Celery, logging) rather than wired by hand.
    """
    if not settings.SENTRY_DSN:
        return False

    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        release=settings.APP_VERSION,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        send_default_pii=False,
        before_send=_scrub,
    )
    return True
