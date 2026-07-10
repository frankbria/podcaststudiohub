"""Analytics service: event ingestion and aggregation"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import Boolean, Float, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..utils.datetime_utils import to_naive_utc, utcnow

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
	# created_at is offset-naive UTC, so normalize caller-supplied bounds to naive UTC
	date_from = utcnow() - timedelta(days=30) if date_from is None else to_naive_utc(date_from)
	date_to = utcnow() if date_to is None else to_naive_utc(date_to)

	window = (
		(AnalyticsEvent.episode_id == episode_id)
		& (AnalyticsEvent.created_at >= date_from)
		& (AnalyticsEvent.created_at <= date_to)
	)

	# Count by event type (GROUP BY instead of a Python loop over all rows)
	counts: Dict[str, int] = {"download": 0, "play": 0, "stream": 0, "share": 0}
	rows = await db.execute(
		select(AnalyticsEvent.event_type, func.count())
		.where(window)
		.group_by(AnalyticsEvent.event_type)
	)
	for event_type, n in rows.all():
		counts[event_type] = counts.get(event_type, 0) + n

	# Device / app / country breakdowns — filter out falsy values to match the
	# old `if event.<field>:` guard (skips both NULL and empty string).
	device_breakdown: Dict[str, int] = {"mobile": 0, "desktop": 0, "tablet": 0, "unknown": 0}
	rows = await db.execute(
		select(AnalyticsEvent.device_type, func.count())
		.where(window & AnalyticsEvent.device_type.isnot(None) & (AnalyticsEvent.device_type != ""))
		.group_by(AnalyticsEvent.device_type)
	)
	for device, n in rows.all():
		device_breakdown[device] = device_breakdown.get(device, 0) + n

	rows = await db.execute(
		select(AnalyticsEvent.app_name, func.count())
		.where(window & AnalyticsEvent.app_name.isnot(None) & (AnalyticsEvent.app_name != ""))
		.group_by(AnalyticsEvent.app_name)
	)
	app_breakdown: Dict[str, int] = {app: n for app, n in rows.all()}

	rows = await db.execute(
		select(AnalyticsEvent.country, func.count())
		.where(window & AnalyticsEvent.country.isnot(None) & (AnalyticsEvent.country != ""))
		.group_by(AnalyticsEvent.country)
	)
	country_counts: Dict[str, int] = {c: n for c, n in rows.all()}

	# Listen duration: sum + count over plays whose JSONB duration is truthy
	# (matches the old `if duration:` guard — excludes missing key, NULL, and 0).
	duration_col = AnalyticsEvent.event_metadata["duration_listened_seconds"].astext.cast(Float)
	total_duration, play_count_for_avg = (
		await db.execute(
			select(func.coalesce(func.sum(duration_col), 0.0), func.count())
			.where(
				window
				& (AnalyticsEvent.event_type == "play")
				& duration_col.isnot(None)
				& (duration_col != 0)
			)
		)
	).one()

	# Completed plays: JSONB `completed` is true (missing/NULL/false excluded)
	completed_col = AnalyticsEvent.event_metadata["completed"].astext.cast(Boolean)
	completed_count = (
		await db.execute(
			select(func.count())
			.where(window & (AnalyticsEvent.event_type == "play") & completed_col.is_(True))
		)
	).scalar_one()

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
	date_to = utcnow()
	date_from = date_to - timedelta(days=days)

	window = (
		(AnalyticsEvent.project_id == project_id)
		& (AnalyticsEvent.created_at >= date_from)
		& (AnalyticsEvent.created_at <= date_to)
	)

	# Download / play totals via GROUP BY event_type
	type_counts = {
		t: n
		for t, n in (
			await db.execute(
				select(AnalyticsEvent.event_type, func.count())
				.where(window)
				.group_by(AnalyticsEvent.event_type)
			)
		).all()
	}
	total_downloads = type_counts.get("download", 0)
	total_plays = type_counts.get("play", 0)

	# Sum listen seconds over plays (missing/NULL duration counts as 0, matching
	# the old `metadata.get("duration_listened_seconds", 0)`).
	duration_col = AnalyticsEvent.event_metadata["duration_listened_seconds"].astext.cast(Float)
	total_listen_seconds = (
		await db.execute(
			select(func.coalesce(func.sum(func.coalesce(duration_col, 0.0)), 0.0))
			.where(window & (AnalyticsEvent.event_type == "play"))
		)
	).scalar_one()

	# Per-episode download breakdown
	episode_downloads: Dict[str, int] = {
		str(eid): n
		for eid, n in (
			await db.execute(
				select(AnalyticsEvent.episode_id, func.count())
				.where(
					window
					& (AnalyticsEvent.event_type == "download")
					& AnalyticsEvent.episode_id.isnot(None)
				)
				.group_by(AnalyticsEvent.episode_id)
			)
		).all()
	}

	# Weekly buckets: GROUP BY day in SQL (O(days), not O(events)), then bucket
	# by Python's "%Y-W%W" so the key format stays byte-for-byte identical
	# (Postgres ISO/`to_char` week numbering would NOT match strftime("%W")).
	weekly: Dict[str, int] = {}
	day_rows = await db.execute(
		select(func.date(AnalyticsEvent.created_at), func.count())
		.where(window)
		.group_by(func.date(AnalyticsEvent.created_at))
	)
	for day, n in day_rows.all():
		week_key = day.strftime("%Y-W%W")
		weekly[week_key] = weekly.get(week_key, 0) + n

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
