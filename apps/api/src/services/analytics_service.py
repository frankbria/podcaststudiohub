"""Analytics service: event ingestion and aggregation"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.analytics_event import (
	AnalyticsEvent,
	VALID_EVENT_TYPES,
	detect_app_name,
	detect_device_type,
	hash_ip,
)

logger = logging.getLogger(__name__)


async def track_event(
	db: AsyncSession,
	tenant_id: UUID,
	event_type: str,
	episode_id: Optional[UUID] = None,
	project_id: Optional[UUID] = None,
	user_agent: Optional[str] = None,
	referer: Optional[str] = None,
	ip_address: Optional[str] = None,
	event_metadata: Optional[Dict[str, Any]] = None,
) -> AnalyticsEvent:
	"""Persist a single engagement event. IP is hashed before storage."""
	if event_type not in VALID_EVENT_TYPES:
		raise ValueError(f"Invalid event_type: {event_type}")

	hashed_ip = hash_ip(ip_address) if ip_address else None
	device_type = detect_device_type(user_agent or "")
	app_name = detect_app_name(user_agent or "")

	event = AnalyticsEvent(
		tenant_id=tenant_id,
		episode_id=episode_id,
		project_id=project_id,
		event_type=event_type,
		user_agent=user_agent,
		referer=referer,
		ip_address=hashed_ip,
		device_type=device_type,
		app_name=app_name,
		event_metadata=event_metadata,
	)
	db.add(event)
	await db.commit()
	await db.refresh(event)
	return event


async def get_episode_analytics(
	db: AsyncSession,
	episode_id: UUID,
	date_from: Optional[datetime] = None,
	date_to: Optional[datetime] = None,
) -> Dict[str, Any]:
	"""Aggregate analytics events for an episode within a date range."""
	if date_from is None:
		date_from = datetime.utcnow() - timedelta(days=30)
	if date_to is None:
		date_to = datetime.utcnow()

	base_query = (
		select(AnalyticsEvent)
		.where(AnalyticsEvent.episode_id == episode_id)
		.where(AnalyticsEvent.created_at >= date_from)
		.where(AnalyticsEvent.created_at <= date_to)
	)

	result = await db.execute(base_query)
	events = result.scalars().all()

	# Count by event type
	counts: Dict[str, int] = {"download": 0, "play": 0, "stream": 0, "share": 0}
	device_breakdown: Dict[str, int] = {"mobile": 0, "desktop": 0, "tablet": 0, "unknown": 0}
	app_breakdown: Dict[str, int] = {}
	country_counts: Dict[str, int] = {}

	total_duration = 0.0
	completed_count = 0
	play_count_for_avg = 0

	for event in events:
		counts[event.event_type] = counts.get(event.event_type, 0) + 1

		if event.device_type:
			device_breakdown[event.device_type] = device_breakdown.get(event.device_type, 0) + 1

		if event.app_name:
			app_breakdown[event.app_name] = app_breakdown.get(event.app_name, 0) + 1

		if event.country:
			country_counts[event.country] = country_counts.get(event.country, 0) + 1

		if event.event_metadata and event.event_type == "play":
			duration = event.event_metadata.get("duration_listened_seconds", 0)
			if duration:
				total_duration += duration
				play_count_for_avg += 1
			if event.event_metadata.get("completed", False):
				completed_count += 1

	total_plays = counts["play"]
	avg_duration = total_duration / play_count_for_avg if play_count_for_avg > 0 else 0.0
	completion_rate = completed_count / total_plays if total_plays > 0 else 0.0

	# Top countries sorted by downloads descending
	top_countries = sorted(
		[{"country": c, "downloads": n} for c, n in country_counts.items()],
		key=lambda x: x["downloads"],
		reverse=True,
	)[:10]

	return {
		"episode_id": episode_id,
		"period": {"from": date_from, "to": date_to},
		"metrics": {
			"total_downloads": counts["download"],
			"total_plays": counts["play"],
			"total_streams": counts["stream"],
			"average_listen_duration_seconds": avg_duration,
			"completion_rate": completion_rate,
		},
		"device_breakdown": device_breakdown,
		"app_breakdown": app_breakdown,
		"top_countries": top_countries,
	}


async def get_project_analytics(
	db: AsyncSession,
	project_id: UUID,
	days: int = 30,
) -> Dict[str, Any]:
	"""Aggregate analytics for an entire project, returning a dashboard summary."""
	date_to = datetime.utcnow()
	date_from = date_to - timedelta(days=days)

	result = await db.execute(
		select(AnalyticsEvent)
		.where(AnalyticsEvent.project_id == project_id)
		.where(AnalyticsEvent.created_at >= date_from)
		.where(AnalyticsEvent.created_at <= date_to)
	)
	events = result.scalars().all()

	total_downloads = 0
	total_plays = 0
	total_listen_seconds = 0.0
	episode_downloads: Dict[str, int] = {}

	# Weekly buckets: key = "YYYY-WNN"
	weekly: Dict[str, int] = {}

	for event in events:
		if event.event_type == "download":
			total_downloads += 1
		elif event.event_type == "play":
			total_plays += 1
			if event.event_metadata:
				total_listen_seconds += event.event_metadata.get("duration_listened_seconds", 0)

		# Episode breakdown for downloads
		if event.episode_id and event.event_type == "download":
			key = str(event.episode_id)
			episode_downloads[key] = episode_downloads.get(key, 0) + 1

		# Weekly bucketing
		week_key = event.created_at.strftime("%Y-W%W")
		weekly[week_key] = weekly.get(week_key, 0) + 1

	top_episodes = sorted(
		[{"episode_id": eid, "downloads": cnt} for eid, cnt in episode_downloads.items()],
		key=lambda x: x["downloads"],
		reverse=True,
	)[:10]

	weekly_downloads = [
		{"week": w, "downloads": c} for w, c in sorted(weekly.items())
	]

	total_listen_hours = total_listen_seconds / 3600.0

	return {
		"project_id": project_id,
		"period": {"from": date_from, "to": date_to, "days": days},
		"summary": {
			"total_downloads": total_downloads,
			"total_plays": total_plays,
			"total_listen_hours": round(total_listen_hours, 2),
		},
		"trends": {"weekly_downloads": weekly_downloads},
		"top_episodes": top_episodes,
	}
