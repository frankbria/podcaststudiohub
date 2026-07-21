"""
Celery task for persisting analytics engagement events (issue #322).

The high-cardinality track endpoint used to do an INSERT + commit + refresh per
event on the request path. That write now happens here so the request returns
immediately. The event id and created_at are minted by the caller
(`analytics_service.build_event_payload`) and passed through, so the insert is
idempotent-ish (a duplicate id is a permanent, non-retried drop) and the HTTP
response never needed the row read back.

Runs under `celery_async_session`. `analytics_events` has FORCE ROW LEVEL
SECURITY (migration 014), so tenant context is armed before the insert — the
same precedent as `billing_service` writing on a non-request session. This
keeps the insert correct even if a deployment wires the worker's DATABASE_URL
to the non-privileged (RLS-enforced) role.
"""

import asyncio
import logging
import uuid as uuid_module
from datetime import datetime
from typing import Any, Dict

from celery import Task
from sqlalchemy.exc import IntegrityError

from src.worker import celery_app

logger = logging.getLogger(__name__)


async def _track_event_async(payload: Dict[str, Any]) -> None:
	"""Insert one AnalyticsEvent from a JSON-safe payload under tenant context."""
	from src.database import celery_async_session, set_tenant_context
	from src.models.analytics_event import AnalyticsEvent

	async with celery_async_session() as db:
		# Arm RLS tenant context BEFORE the insert so the WITH CHECK policy on
		# analytics_events passes under an RLS-enforced role.
		await set_tenant_context(db, payload["tenant_id"])

		event = AnalyticsEvent(
			id=uuid_module.UUID(payload["id"]),
			tenant_id=uuid_module.UUID(payload["tenant_id"]),
			episode_id=uuid_module.UUID(payload["episode_id"]) if payload.get("episode_id") else None,
			project_id=uuid_module.UUID(payload["project_id"]) if payload.get("project_id") else None,
			event_type=payload["event_type"],
			user_agent=payload.get("user_agent"),
			referer=payload.get("referer"),
			ip_address=payload.get("ip_address"),
			country=payload.get("country"),
			device_type=payload.get("device_type"),
			app_name=payload.get("app_name"),
			event_metadata=payload.get("event_metadata"),
			created_at=datetime.fromisoformat(payload["created_at"]),
		)
		db.add(event)
		await db.commit()


@celery_app.task(bind=True, name="track_analytics_event", max_retries=3, time_limit=60)
def track_analytics_event_task(self: Task, payload: Dict[str, Any]) -> Dict[str, Any]:
	"""
	Persist a tracked analytics event via Celery (issue #322).

	Transient failures (broker/DB blips) retry with exponential backoff; an
	``IntegrityError`` (duplicate id, or an episode/project deleted between
	request and insert) is a permanent drop — retrying can never succeed.

	Returns a dict with ``status`` ('recorded' or 'dropped').
	"""
	event_id = payload.get("id")
	try:
		asyncio.run(_track_event_async(payload))
		return {"status": "recorded", "id": event_id}

	except IntegrityError as e:
		# Permanent — do not retry. Analytics are fire-and-forget; log and drop.
		logger.warning(f"Analytics event {event_id} dropped (integrity error): {e}")
		return {"status": "dropped", "id": event_id, "error": str(e)}

	except Exception as e:
		retry_countdown = 60 * (2 ** self.request.retries)
		try:
			raise self.retry(exc=e, countdown=retry_countdown)
		except self.MaxRetriesExceededError:
			logger.error(
				f"Analytics event {event_id} dropped after max retries: {e}"
			)
			return {"status": "dropped", "id": event_id, "error": f"Max retries exceeded: {e}"}
