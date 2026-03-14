"""
Analytics service layer for event tracking and aggregation.

Provides functions to track engagement events and query aggregated metrics.
All IP addresses are hashed before storage for privacy compliance.
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..models.analytics_event import AnalyticsEvent
from ..schemas.analytics import AnalyticsEventCreate


def _detect_device_type(user_agent: Optional[str]) -> str:
	"""Detect device type from User-Agent string."""
	if not user_agent:
		return "unknown"
	ua = user_agent.lower()
	if any(kw in ua for kw in ("iphone", "android", "mobile", "blackberry")):
		return "mobile"
	if "tablet" in ua or "ipad" in ua:
		return "tablet"
	if any(kw in ua for kw in ("windows", "macintosh", "linux", "x11")):
		return "desktop"
	return "unknown"


def _detect_app_name(user_agent: Optional[str]) -> Optional[str]:
	"""Detect podcast app from User-Agent string."""
	if not user_agent:
		return None
	ua = user_agent.lower()
	app_map = {
		"apple podcasts": "apple_podcasts",
		"overcast": "overcast",
		"spotify": "spotify",
		"pocketcasts": "pocketcasts",
		"castro": "castro",
		"stitcher": "stitcher",
		"googlepodcasts": "google_podcasts",
	}
	for pattern, app in app_map.items():
		if pattern in ua:
			return app
	return "other"


async def track_event(
	db: AsyncSession,
	tenant_id: UUID,
	event_data: AnalyticsEventCreate,
	user_agent: Optional[str] = None,
	referer: Optional[str] = None,
	ip_address: Optional[str] = None,
) -> AnalyticsEvent:
	"""
	Track a single engagement event.

	Hashes IP address before storage for privacy compliance.
	Detects device type and app name from User-Agent.

	Args:
		db: Database session
		tenant_id: Tenant ID (user.id)
		event_data: Event creation data
		user_agent: Optional User-Agent header
		referer: Optional Referer header
		ip_address: Optional client IP (will be hashed)

	Returns:
		Created AnalyticsEvent instance
	"""
	ip_hash = AnalyticsEvent.hash_ip(ip_address) if ip_address else None
	device_type = _detect_device_type(user_agent)
	app_name = _detect_app_name(user_agent)

	event = AnalyticsEvent(
		tenant_id=tenant_id,
		episode_id=event_data.episode_id,
		project_id=event_data.project_id,
		event_type=event_data.event_type,
		user_agent=user_agent,
		referer=referer,
		ip_hash=ip_hash,
		device_type=device_type,
		app_name=app_name,
		metadata=event_data.metadata,
	)
	db.add(event)
	await db.commit()
	await db.refresh(event)
	return event


async def get_episode_analytics_summary(
	db: AsyncSession,
	episode_id: UUID,
	date_from: Optional[datetime] = None,
	date_to: Optional[datetime] = None,
) -> Dict[str, Any]:
	"""
	Get aggregated analytics for an episode.

	Counts events by type and device breakdown for the given period.

	Args:
		db: Database session
		episode_id: Episode UUID to query
		date_from: Start of period (default: 30 days ago)
		date_to: End of period (default: now)

	Returns:
		Dictionary with metrics, device_breakdown, and period info
	"""
	if date_to is None:
		date_to = datetime.utcnow()
	if date_from is None:
		date_from = date_to - timedelta(days=30)

	# Count by event type
	type_counts_query = (
		select(AnalyticsEvent.event_type, func.count().label("count"))
		.where(
			AnalyticsEvent.episode_id == episode_id,
			AnalyticsEvent.created_at >= date_from,
			AnalyticsEvent.created_at <= date_to,
		)
		.group_by(AnalyticsEvent.event_type)
	)
	type_result = await db.execute(type_counts_query)
	type_counts = {row.event_type: row.count for row in type_result}

	# Count by device type
	device_query = (
		select(AnalyticsEvent.device_type, func.count().label("count"))
		.where(
			AnalyticsEvent.episode_id == episode_id,
			AnalyticsEvent.created_at >= date_from,
			AnalyticsEvent.created_at <= date_to,
		)
		.group_by(AnalyticsEvent.device_type)
	)
	device_result = await db.execute(device_query)
	device_breakdown = {row.device_type or "unknown": row.count for row in device_result}

	return {
		"episode_id": str(episode_id),
		"period": {
			"from": date_from.isoformat() + "Z",
			"to": date_to.isoformat() + "Z",
		},
		"metrics": {
			"total_downloads": type_counts.get("download", 0),
			"total_plays": type_counts.get("play", 0),
			"total_streams": type_counts.get("stream", 0),
			"total_shares": type_counts.get("share", 0),
		},
		"device_breakdown": device_breakdown,
	}


async def get_project_analytics_summary(
	db: AsyncSession,
	project_id: UUID,
	days: int = 30,
) -> Dict[str, Any]:
	"""
	Get aggregated analytics dashboard summary for a project.

	Aggregates all episode events for the project within the given period.

	Args:
		db: Database session
		project_id: Project UUID to query
		days: Number of days to look back (default: 30)

	Returns:
		Dictionary with summary metrics and top episodes
	"""
	date_to = datetime.utcnow()
	date_from = date_to - timedelta(days=days)

	# Count by event type for the project
	type_counts_query = (
		select(AnalyticsEvent.event_type, func.count().label("count"))
		.where(
			AnalyticsEvent.project_id == project_id,
			AnalyticsEvent.created_at >= date_from,
			AnalyticsEvent.created_at <= date_to,
		)
		.group_by(AnalyticsEvent.event_type)
	)
	type_result = await db.execute(type_counts_query)
	type_counts = {row.event_type: row.count for row in type_result}

	# Top episodes by download count
	top_episodes_query = (
		select(AnalyticsEvent.episode_id, func.count().label("count"))
		.where(
			AnalyticsEvent.project_id == project_id,
			AnalyticsEvent.event_type == "download",
			AnalyticsEvent.episode_id.isnot(None),
			AnalyticsEvent.created_at >= date_from,
			AnalyticsEvent.created_at <= date_to,
		)
		.group_by(AnalyticsEvent.episode_id)
		.order_by(func.count().desc())
		.limit(5)
	)
	top_episodes_result = await db.execute(top_episodes_query)
	top_episodes: List[Dict[str, Any]] = [
		{"episode_id": str(row.episode_id), "downloads": row.count}
		for row in top_episodes_result
	]

	return {
		"project_id": str(project_id),
		"period": {
			"from": date_from.isoformat() + "Z",
			"to": date_to.isoformat() + "Z",
			"days": days,
		},
		"summary": {
			"total_downloads": type_counts.get("download", 0),
			"total_plays": type_counts.get("play", 0),
			"total_streams": type_counts.get("stream", 0),
			"total_shares": type_counts.get("share", 0),
		},
		"top_episodes": top_episodes,
	}
