"""Drop-in replacement for the deprecated datetime.utcnow().

Model columns are DateTime WITHOUT time zone, so this must return a naive
datetime (asyncpg rejects aware values for those columns). Callers that need
aware datetimes should use datetime.now(timezone.utc) directly.
"""
from datetime import datetime, timezone


def utcnow() -> datetime:
	"""Current UTC time as a naive datetime — what datetime.utcnow() returned."""
	return datetime.now(timezone.utc).replace(tzinfo=None)


def to_naive_utc(dt: datetime) -> datetime:
	"""Normalize a possibly-aware datetime to naive UTC for naive-column comparison."""
	if dt.tzinfo:
		return dt.astimezone(timezone.utc).replace(tzinfo=None)
	return dt
