"""Tests for src.utils.datetime_utils.utcnow — the datetime.utcnow() replacement.

Model columns are DateTime WITHOUT time zone, so the helper must stay naive
(asyncpg rejects aware datetimes for those columns) while matching UTC wall time.
"""
from datetime import datetime, timezone

from src.utils.datetime_utils import utcnow


def test_utcnow_is_naive():
	assert utcnow().tzinfo is None


def test_utcnow_matches_utc_wall_time():
	aware = datetime.now(timezone.utc).replace(tzinfo=None)
	delta = abs((utcnow() - aware).total_seconds())
	assert delta < 5
