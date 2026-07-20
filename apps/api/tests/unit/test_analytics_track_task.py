"""
Unit tests for the analytics event Celery task (issue #322).

The per-event INSERT + commit moved off the request path into
track_analytics_event_task. These cover the async helper (arms tenant context,
inserts the exact id/created_at, commits once) and the task surface (retry vs
permanent-drop policy), with celery_async_session and set_tenant_context mocked
— mirroring test_extract_content_async.py / test_url_reachability_task.py.
"""

import inspect
from datetime import datetime
from uuid import uuid4

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.exc import IntegrityError


def _make_async_context_manager(db_mock):
	cm = AsyncMock()
	cm.__aenter__ = AsyncMock(return_value=db_mock)
	cm.__aexit__ = AsyncMock(return_value=False)
	return cm


def _payload(**over):
	p = {
		"id": str(uuid4()),
		"tenant_id": str(uuid4()),
		"episode_id": str(uuid4()),
		"project_id": None,
		"event_type": "play",
		"user_agent": "UA",
		"referer": None,
		"ip_address": "hashed-ip",
		"device_type": "mobile",
		"app_name": "spotify",
		"event_metadata": {"completed": True},
		"created_at": "2026-07-19T12:00:00",
	}
	p.update(over)
	return p


@pytest.mark.asyncio
async def test_track_async_arms_tenant_context_then_inserts_and_commits():
	"""set_tenant_context is armed BEFORE the insert; id/created_at are preserved."""
	from src.tasks.analytics import _track_event_async

	mock_db = AsyncMock()
	calls = []

	async def _stc(db, tid):
		calls.append(("set_tenant", tid))

	def _add(obj):
		calls.append(("add", obj))

	mock_db.add = MagicMock(side_effect=_add)
	payload = _payload()

	with patch("src.database.celery_async_session", return_value=_make_async_context_manager(mock_db)), \
	     patch("src.database.set_tenant_context", AsyncMock(side_effect=_stc)):
		await _track_event_async(payload)

	# Tenant context is armed before the row is added (RLS WITH CHECK).
	assert calls[0] == ("set_tenant", payload["tenant_id"])
	assert calls[1][0] == "add"
	added = calls[1][1]
	assert str(added.id) == payload["id"]
	assert str(added.tenant_id) == payload["tenant_id"]
	assert str(added.episode_id) == payload["episode_id"]
	assert added.project_id is None
	assert added.event_type == "play"
	assert added.created_at == datetime.fromisoformat(payload["created_at"])
	mock_db.commit.assert_awaited_once()


def test_task_returns_recorded_on_success():
	from src.tasks.analytics import track_analytics_event_task

	with patch("src.tasks.analytics._track_event_async", MagicMock()), \
	     patch("src.tasks.analytics.asyncio.run", MagicMock(return_value=None)):
		with patch.object(track_analytics_event_task, "update_state"):
			result = track_analytics_event_task.run(payload=_payload(id="evt-1"))

	assert result["status"] == "recorded"
	assert result["id"] == "evt-1"


def test_task_drops_on_integrity_error_without_retry():
	"""A duplicate id / vanished FK is permanent — drop, never retry."""
	from src.tasks.analytics import track_analytics_event_task

	err = IntegrityError("INSERT", {}, Exception("duplicate key"))
	with patch("src.tasks.analytics._track_event_async", MagicMock()), \
	     patch("src.tasks.analytics.asyncio.run", MagicMock(side_effect=err)):
		with patch.object(track_analytics_event_task, "update_state"), \
		     patch.object(track_analytics_event_task, "retry") as mock_retry:
			result = track_analytics_event_task.run(payload=_payload())

	assert result["status"] == "dropped"
	mock_retry.assert_not_called()


def test_task_retries_on_transient_error():
	from src.tasks.analytics import track_analytics_event_task

	with patch("src.tasks.analytics._track_event_async", MagicMock()), \
	     patch("src.tasks.analytics.asyncio.run", MagicMock(side_effect=ConnectionError("boom"))):
		with patch.object(track_analytics_event_task, "update_state"), \
		     patch.object(
		         track_analytics_event_task,
		         "retry",
		         side_effect=track_analytics_event_task.MaxRetriesExceededError(),
		     ) as mock_retry:
			result = track_analytics_event_task.run(payload=_payload())

	assert result["status"] == "dropped"
	mock_retry.assert_called_once()


def test_task_signature_accepts_payload():
	from src.tasks.analytics import track_analytics_event_task
	assert "payload" in inspect.signature(track_analytics_event_task.run).parameters
