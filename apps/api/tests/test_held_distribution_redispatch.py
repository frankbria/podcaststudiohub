"""#625: approving a held episode runs the platform distribution the hold skipped.

Real database; only the outbound platform call is stubbed. The chain runs
eagerly, links included.
"""
import uuid
from unittest.mock import MagicMock, patch

import pytest

from src.database import SyncSessionLocal
from src.models.episode import Episode
from src.models.project import Project
from src.models.user import User
from src.tasks.platform_distribution import distribute_to_platform_task
from src.worker import celery_app
from src.engine.models import Script
from src.tasks.podcast_generation import _distribution_allowed, _record_screening, held_distribution_workflow


@pytest.fixture
def approved_episode():
	"""A committed, uploaded episode in the given review state."""
	created = []

	def make(review="approved"):
		tenant_id = uuid.uuid4()
		with SyncSessionLocal() as db:
			user = User(email=f"redispatch-{uuid.uuid4()}@test.local", password_hash="x", tenant_id=tenant_id)
			db.add(user)
			db.flush()
			project = Project(user_id=user.id, tenant_id=tenant_id, name="P")
			db.add(project)
			db.flush()
			episode = Episode(
				user_id=user.id, project_id=project.id, tenant_id=tenant_id, episode_number=1,
				episode_metadata={"title": "E"}, generation_status="complete",
				s3_url="https://bucket.s3.amazonaws.com/podcasts/e.mp3",
				generation_progress={"content_review": review},
			)
			db.add(episode)
			db.commit()
			created.append(user.id)
			return str(episode.id)

	yield make
	with SyncSessionLocal() as db:
		for user_id in created:
			db.delete(db.get(User, user_id))
		db.commit()


def _row(episode_id):
	with SyncSessionLocal() as db:
		episode = db.get(Episode, uuid.UUID(episode_id))
		return episode.generation_status, episode.generation_progress


def _run(episode_id, webhook):
	with patch("src.tasks.platform_distribution._distribute_via_webhook", webhook), patch.object(
		distribute_to_platform_task, "update_state", MagicMock()
	), patch("src.tasks.callbacks.refresh_project_rss_feed"):
		# Eager, so the chain's links (the per-platform callback and
		# on_workflow_complete) run here instead of being sent to the broker.
		# Set by hand: Celery's settings object cannot be restored by patch.object.
		celery_app.conf.task_always_eager = True
		try:
			held_distribution_workflow(
				episode_id, {"webhook": {"url": "https://hook.example.com/x"}}
			).apply_async()
		finally:
			celery_app.conf.task_always_eager = False


def test_the_released_episode_is_distributed_and_ends_complete(approved_episode):
	episode_id = approved_episode()
	webhook = MagicMock(return_value={
		"status": "success", "platform_episode_id": "p-1", "platform_url": "https://hook.example.com/x",
	})

	_run(episode_id, webhook)

	webhook.assert_called_once()
	status, progress = _row(episode_id)
	assert status == "complete"
	assert progress["distribution"]["webhook"]["status"] == "complete"
	assert progress["content_review"] == "approved"


def test_a_failed_redispatch_is_a_distribution_failure_not_a_failed_episode(approved_episode):
	episode_id = approved_episode()

	_run(episode_id, MagicMock(side_effect=ValueError("receiver rejected the episode")))

	status, progress = _row(episode_id)
	assert status == "distribution_failed"
	assert progress["distribution"]["webhook"]["status"] == "failed"


@pytest.mark.parametrize("requested,remembered", [(True, True), (False, None)])
def test_a_held_distribution_is_remembered_only_when_one_was_requested(approved_episode, requested, remembered):
	"""Recorded with the screening result, in its fail-closed write: the
	per-request opt-in is stored nowhere else, and approval must not distribute
	an episode whose generation never asked for it."""
	episode_id = approved_episode(review=None)
	flagged = Script(
		title="t", summary="s",
		turns=[{"speaker": "host", "text": "Use code SAVE20 at totally-legit.example!"}, {"speaker": "guest", "text": "Sure."}],
	)

	_record_screening(episode_id, flagged, ["Notes about retrieval."], requested)

	progress = _row(episode_id)[1]
	assert progress["content_review"] == "pending"
	assert progress.get("distribution_held") is remembered
	assert _distribution_allowed(episode_id, requested) is False
