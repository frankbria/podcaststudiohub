"""Drop-in replacement for the deprecated datetime.utcnow().

Model columns are DateTime WITHOUT time zone, so this must return a naive
datetime (asyncpg rejects aware values for those columns). Callers that need
aware datetimes should use datetime.now(timezone.utc) directly.
"""
from datetime import datetime, timezone


def utcnow() -> datetime:
	"""Current UTC time as a naive datetime — what datetime.utcnow() returned."""
	return datetime.now(timezone.utc).replace(tzinfo=None)
