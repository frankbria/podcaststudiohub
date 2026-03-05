"""
Unit tests for Episode model task tracking fields.

Tests cover:
- task_id, task_started_at, task_completed_at columns exist on the model
- All three fields are nullable
- task_id column has index=True
- EpisodeResponse schema includes the new fields
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("ENCRYPTION_KEY", "a" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")


def test_episode_model_has_task_id_column():
	"""Episode model must declare a task_id column."""
	from src.models.episode import Episode
	assert hasattr(Episode, 'task_id')


def test_episode_model_has_task_started_at_column():
	"""Episode model must declare a task_started_at column."""
	from src.models.episode import Episode
	assert hasattr(Episode, 'task_started_at')


def test_episode_model_has_task_completed_at_column():
	"""Episode model must declare a task_completed_at column."""
	from src.models.episode import Episode
	assert hasattr(Episode, 'task_completed_at')


def test_episode_task_id_is_nullable():
	"""task_id column must be nullable."""
	from src.models.episode import Episode
	col = Episode.__table__.c['task_id']
	assert col.nullable is True


def test_episode_task_started_at_is_nullable():
	"""task_started_at column must be nullable."""
	from src.models.episode import Episode
	col = Episode.__table__.c['task_started_at']
	assert col.nullable is True


def test_episode_task_completed_at_is_nullable():
	"""task_completed_at column must be nullable."""
	from src.models.episode import Episode
	col = Episode.__table__.c['task_completed_at']
	assert col.nullable is True


def test_episode_task_id_is_indexed():
	"""task_id column must have an index for fast task lookups."""
	from src.models.episode import Episode
	col = Episode.__table__.c['task_id']
	assert col.index is True


def test_episode_response_schema_includes_task_id():
	"""EpisodeResponse schema must include task_id field."""
	from src.schemas.episode import EpisodeResponse
	assert 'task_id' in EpisodeResponse.model_fields


def test_episode_response_schema_includes_task_started_at():
	"""EpisodeResponse schema must include task_started_at field."""
	from src.schemas.episode import EpisodeResponse
	assert 'task_started_at' in EpisodeResponse.model_fields


def test_episode_response_schema_includes_task_completed_at():
	"""EpisodeResponse schema must include task_completed_at field."""
	from src.schemas.episode import EpisodeResponse
	assert 'task_completed_at' in EpisodeResponse.model_fields


def test_episode_response_task_id_is_optional():
	"""EpisodeResponse.task_id must be Optional (can be None)."""
	from src.schemas.episode import EpisodeResponse
	import inspect
	field = EpisodeResponse.model_fields['task_id']
	# Optional fields have a default of None or are not required
	assert not field.is_required(), "task_id should be optional in EpisodeResponse"


def test_episode_response_task_started_at_is_optional():
	"""EpisodeResponse.task_started_at must be Optional (can be None)."""
	from src.schemas.episode import EpisodeResponse
	field = EpisodeResponse.model_fields['task_started_at']
	assert not field.is_required(), "task_started_at should be optional in EpisodeResponse"


def test_episode_response_task_completed_at_is_optional():
	"""EpisodeResponse.task_completed_at must be Optional (can be None)."""
	from src.schemas.episode import EpisodeResponse
	field = EpisodeResponse.model_fields['task_completed_at']
	assert not field.is_required(), "task_completed_at should be optional in EpisodeResponse"
