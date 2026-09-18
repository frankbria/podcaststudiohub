"""
Issue #526: a transient distribution error that exhausts its retries is a
per-platform ``distribution_failed``, not a whole-episode ``failed``.

Runs against the real database. Only the outbound platform call is stubbed
(it is the external service); Celery's own ``retry()`` decides exhaustion,
exactly as a worker would.
"""
import uuid
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.database import SyncSessionLocal
from src.models.episode import Episode
from src.models.project import Project
from src.models.user import User
from src.tasks.callbacks import on_distribution_complete, on_workflow_complete
from src.tasks.platform_distribution import distribute_to_platform_task


@pytest.fixture
def uploaded_episode():
	"""A committed episode whose audio is already uploaded (s3_url set)."""
	tenant_id = uuid.uuid4()
	with SyncSessionLocal() as db:
		user = User(
			email=f"dist-exhaust-{uuid.uuid4()}@test.local",
			password_hash="x",
			tenant_id=tenant_id,
		)
		db.add(user)
		db.flush()
		project = Project(user_id=user.id, tenant_id=tenant_id, name="P")
		db.add(project)
		db.flush()
		episode = Episode(
			user_id=user.id,
			project_id=project.id,
			tenant_id=tenant_id,
			episode_number=1,
			episode_metadata={"title": "E"},
			generation_status="uploading",
			s3_url="https://bucket.s3.amazonaws.com/podcasts/e.mp3",
		)
		db.add(episode)
		db.commit()
		episode_id, user_id = str(episode.id), user.id
	yield episode_id
	with SyncSessionLocal() as db:
		db.delete(db.get(User, user_id))
		db.commit()


def _run_exhausted(episode_id, platform, webhook):
	"""Run the task on its final attempt, with no retry mock."""
	with patch(
		"src.tasks.platform_distribution._distribute_via_webhook", webhook
	), patch.object(distribute_to_platform_task, "update_state", MagicMock()):
		distribute_to_platform_task.push_request(
			retries=distribute_to_platform_task.max_retries,
			called_directly=False,
			id=f"exhausted-{platform}",
		)
		try:
			return distribute_to_platform_task.run(
				episode_id=episode_id,
				platform=platform,
				platform_config={"url": "https://hook.example.com/x"},
				episode_metadata={},
			)
		finally:
			distribute_to_platform_task.pop_request()


def test_exhausted_transient_error_is_per_platform_distribution_failed(
	uploaded_episode,
):
	result = _run_exhausted(
		uploaded_episode,
		"webhook",
		MagicMock(side_effect=requests.ConnectionError("receiver down")),
	)

	# Returned, not raised: the chain continues to later platforms.
	assert result["status"] == "failed"
	assert "receiver down" in result["error"]
	assert "retries" in result["error"]

	on_distribution_complete.run(result, episode_id=uploaded_episode, platform="webhook")
	with patch("src.tasks.callbacks.refresh_project_rss_feed"):
		on_workflow_complete.run({}, episode_id=uploaded_episode)

	with SyncSessionLocal() as db:
		episode = db.get(Episode, uuid.UUID(uploaded_episode))
		assert episode.generation_status == "distribution_failed"
		progress = episode.generation_progress
		assert progress["failed_platforms"] == ["webhook"]
		assert progress["distribution"]["webhook"]["status"] == "failed"
		assert "receiver down" in progress["distribution"]["webhook"]["error"]
		assert episode.s3_url  # audio stays usable


def test_exhausted_wait_for_audio_still_fails_the_episode(uploaded_episode):
	"""Giving up on a missing upload is not a distribution outcome: no audio
	means the episode is 'failed', never 'distribution_failed'."""
	with SyncSessionLocal() as db:
		db.get(Episode, uuid.UUID(uploaded_episode)).s3_url = None
		db.commit()
	webhook = MagicMock()

	result = _run_exhausted(uploaded_episode, "webhook", webhook)

	webhook.assert_not_called()
	on_distribution_complete.run(result, episode_id=uploaded_episode, platform="webhook")
	on_workflow_complete.run({}, episode_id=uploaded_episode)

	with SyncSessionLocal() as db:
		episode = db.get(Episode, uuid.UUID(uploaded_episode))
		assert episode.generation_status == "failed"


def test_failure_is_recorded_before_the_task_returns(uploaded_episode):
	"""On the last platform, on_distribution_complete and on_workflow_complete
	are dispatched as an unordered group; if on_workflow_complete wins, it must
	already see the failure, so the task records it in-task."""
	result = _run_exhausted(
		uploaded_episode,
		"webhook",
		MagicMock(side_effect=requests.ConnectionError("receiver down")),
	)

	with SyncSessionLocal() as db:
		entry = db.get(Episode, uuid.UUID(uploaded_episode)).generation_progress[
			"distribution"
		]["webhook"]
		assert entry["status"] == "failed"

	# on_workflow_complete wins the race: on_distribution_complete has not run.
	on_workflow_complete.run({}, episode_id=uploaded_episode)
	with SyncSessionLocal() as db:
		assert (
			db.get(Episode, uuid.UUID(uploaded_episode)).generation_status
			== "distribution_failed"
		)
	assert result["status"] == "failed"
