"""Observability baseline tests (issue #320).

Pins four contracts:
1. JSON log records carry request_id + tenant_id, so an incident is filterable.
2. Every request gets an X-Request-ID, echoed back; a client-supplied one wins.
3. The correlation/tenant ids ride Celery message headers from API to task,
   without touching any task signature.
4. Sentry stays off unless SENTRY_DSN is set, and scrubs bodies/creds when on.
"""
import json
import logging
import uuid
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient

from src.logging_config import (
    CORRELATION_ID,
    REQUEST_ID_HEADER,
    TENANT_ID,
    JsonFormatter,
    _scrub,
    build_formatter,
    init_sentry,
    setup_logging,
)


def _record(**kwargs) -> logging.LogRecord:
    defaults = dict(
        name="src.test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="hello", args=(), exc_info=None,
    )
    defaults.update(kwargs)
    return logging.LogRecord(**defaults)


# ── AC5: JSON formatter ────────────────────────────────────────────────────


def test_formatter_emits_parseable_json_with_core_fields():
    payload = json.loads(JsonFormatter().format(_record()))

    assert payload["message"] == "hello"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "src.test"
    assert "timestamp" in payload


def test_formatter_binds_request_and_tenant_id():
    """The whole point of AC3: a log line must say which request/tenant it came from."""
    request_token = CORRELATION_ID.set("req-abc")
    tenant_token = TENANT_ID.set("tenant-xyz")
    try:
        payload = json.loads(JsonFormatter().format(_record()))
    finally:
        CORRELATION_ID.reset(request_token)
        TENANT_ID.reset(tenant_token)

    assert payload["request_id"] == "req-abc"
    assert payload["tenant_id"] == "tenant-xyz"


def test_formatter_omits_ids_when_unbound():
    payload = json.loads(JsonFormatter().format(_record()))
    assert "request_id" not in payload
    assert "tenant_id" not in payload


def test_formatter_renders_exception_and_extra_fields():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = _record(exc_info=sys.exc_info())
    record.episode_id = uuid.UUID("11111111-1111-1111-1111-111111111111")

    payload = json.loads(JsonFormatter().format(record))

    assert "ValueError: boom" in payload["exception"]
    # Non-JSON-native values must not blow up the formatter.
    assert payload["episode_id"] == "11111111-1111-1111-1111-111111111111"


def test_formatter_message_interpolates_args():
    payload = json.loads(JsonFormatter().format(_record(msg="hi %s", args=("bob",))))
    assert payload["message"] == "hi bob"


def test_log_format_setting_selects_formatter():
    with patch("src.logging_config.settings.LOG_FORMAT", "json"):
        assert isinstance(build_formatter(), JsonFormatter)
    with patch("src.logging_config.settings.LOG_FORMAT", "text"):
        assert not isinstance(build_formatter(), JsonFormatter)


def test_setup_logging_also_formats_uvicorn_handlers():
    """AC5 says 'shared by uvicorn and Celery' — uvicorn's handlers don't
    propagate to root, so configuring root alone would leave access logs raw."""
    access = logging.getLogger("uvicorn.access")
    handler = logging.StreamHandler()
    access.addHandler(handler)
    try:
        with patch("src.logging_config.settings.LOG_FORMAT", "json"):
            setup_logging()
        assert isinstance(handler.formatter, JsonFormatter)
    finally:
        access.removeHandler(handler)


# ── AC3: correlation ID over HTTP ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_response_carries_generated_request_id(client: AsyncClient):
    response = await client.get("/health")

    assert response.status_code == 200
    # Must be present and a well-formed uuid, not an empty string.
    uuid.UUID(response.headers[REQUEST_ID_HEADER])


@pytest.mark.asyncio
async def test_client_supplied_request_id_is_reused(client: AsyncClient):
    """Lets a caller (or nginx) stitch its own trace to ours."""
    response = await client.get("/health", headers={REQUEST_ID_HEADER: "trace-me-123"})

    assert response.headers[REQUEST_ID_HEADER] == "trace-me-123"


@pytest.mark.asyncio
async def test_request_ids_differ_across_requests(client: AsyncClient):
    first = await client.get("/health")
    second = await client.get("/health")

    assert first.headers[REQUEST_ID_HEADER] != second.headers[REQUEST_ID_HEADER]


@pytest.mark.asyncio
async def test_correlation_id_does_not_leak_after_request(client: AsyncClient):
    await client.get("/health")
    assert CORRELATION_ID.get() is None


# ── AC3: propagation into Celery ───────────────────────────────────────────


def test_publish_stamps_ids_onto_message_headers():
    from src.worker import (
        CORRELATION_ID_HEADER,
        TENANT_ID_HEADER,
        _propagate_context_to_task,
    )

    request_token = CORRELATION_ID.set("req-1")
    tenant_token = TENANT_ID.set("tenant-1")
    try:
        headers = {}
        _propagate_context_to_task(headers=headers)
    finally:
        CORRELATION_ID.reset(request_token)
        TENANT_ID.reset(tenant_token)

    assert headers[CORRELATION_ID_HEADER] == "req-1"
    assert headers[TENANT_ID_HEADER] == "tenant-1"


def test_publish_mints_id_when_outside_request_context():
    """Beat tasks (reap_stuck_episodes) publish with no request in scope; they
    still need a groupable id."""
    from src.worker import CORRELATION_ID_HEADER, _propagate_context_to_task

    headers = {}
    _propagate_context_to_task(headers=headers)

    uuid.UUID(headers[CORRELATION_ID_HEADER])


def test_prerun_binds_ids_from_message_headers():
    from src.worker import (
        CORRELATION_ID_HEADER,
        TENANT_ID_HEADER,
        _bind_task_context,
        _unbind_task_context,
    )

    task = MagicMock()
    task.request = MagicMock(
        **{CORRELATION_ID_HEADER: "req-2", TENANT_ID_HEADER: "tenant-2"}
    )
    try:
        _bind_task_context(task=task)
        assert CORRELATION_ID.get() == "req-2"
        assert TENANT_ID.get() == "tenant-2"
    finally:
        _unbind_task_context()


def test_postrun_clears_ids_so_pooled_worker_cannot_leak_tenant():
    from src.worker import _unbind_task_context

    CORRELATION_ID.set("req-3")
    TENANT_ID.set("tenant-3")

    _unbind_task_context()

    assert CORRELATION_ID.get() is None
    assert TENANT_ID.get() is None


def test_api_to_task_roundtrip_preserves_id():
    """The end-to-end contract: what the API publishes is what the task binds."""
    from src.worker import (
        TENANT_ID_HEADER,
        _bind_task_context,
        _propagate_context_to_task,
        _unbind_task_context,
    )

    headers = {}
    request_token = CORRELATION_ID.set("end-to-end")
    tenant_token = TENANT_ID.set("tenant-e2e")
    try:
        _propagate_context_to_task(headers=headers)
    finally:
        CORRELATION_ID.reset(request_token)
        TENANT_ID.reset(tenant_token)

    assert CORRELATION_ID.get() is None  # publisher context gone, as in a worker

    task = MagicMock()
    task.request = MagicMock(**{k: v for k, v in headers.items()})
    try:
        _bind_task_context(task=task)
        assert CORRELATION_ID.get() == "end-to-end"
        assert TENANT_ID.get() == "tenant-e2e"
    finally:
        _unbind_task_context()

    assert headers[TENANT_ID_HEADER] == "tenant-e2e"


# ── AC1: Sentry ────────────────────────────────────────────────────────────


def test_sentry_is_noop_without_dsn():
    """Tests/CI/local must never phone home."""
    with patch("src.logging_config.settings.SENTRY_DSN", None):
        assert init_sentry() is False


def test_sentry_initialises_with_dsn_and_pii_disabled():
    with patch("src.logging_config.settings.SENTRY_DSN", "https://k@example.com/1"), \
            patch("src.logging_config.settings.ENVIRONMENT", "staging"), \
            patch("sentry_sdk.init") as mock_init:
        assert init_sentry() is True

    kwargs = mock_init.call_args.kwargs
    assert kwargs["dsn"] == "https://k@example.com/1"
    assert kwargs["environment"] == "staging"
    assert kwargs["send_default_pii"] is False
    assert kwargs["traces_sample_rate"] == 0.0


def test_sentry_before_send_scrubs_body_and_credentials():
    """Multi-tenant app: request bodies hold other tenants' content."""
    event = {
        "request": {
            "data": {"secret": "podcast script"},
            "cookies": {"session": "abc"},
            "headers": {"Authorization": "Bearer tok", "User-Agent": "curl"},
        }
    }

    scrubbed = _scrub(event, {})

    assert "data" not in scrubbed["request"]
    assert "cookies" not in scrubbed["request"]
    assert "Authorization" not in scrubbed["request"]["headers"]
    assert scrubbed["request"]["headers"]["User-Agent"] == "curl"


def test_sentry_before_send_tolerates_event_without_request():
    assert _scrub({"level": "error"}, {}) == {"level": "error"}
