"""
Unit tests for issue #211 distribution-metadata population.

The workflow builder passes an empty ``episode_metadata`` because the audio's
``s3_url`` is only set by the upload stage that runs before distribution. The
distribution task therefore loads the Episode and builds real metadata; these
tests cover the merge helper and the task's population behaviour with the DB and
platform services mocked.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def _episode(**overrides):
	"""Build an Episode-like object with sensible defaults."""
	data = {
		"episode_metadata": {
			"title": "My Episode",
			"description": "A great episode",
			"explicit": True,
			"publication_date": "2026-01-15",
		},
		"duration_seconds": 123.0,
		"s3_url": "https://bucket.s3.amazonaws.com/podcasts/episode-1.mp3",
		"project_id": "00000000-0000-0000-0000-0000000000aa",
	}
	data.update(overrides)
	return SimpleNamespace(**data)


class TestMergeEpisodeMetadata:
	"""Tests for ``_merge_episode_metadata``."""

	def test_builds_metadata_from_db_fields(self):
		from src.tasks.platform_distribution import _merge_episode_metadata

		merged = _merge_episode_metadata(_episode(), {})

		assert merged["title"] == "My Episode"
		assert merged["description"] == "A great episode"
		assert merged["audio_url"] == (
			"https://bucket.s3.amazonaws.com/podcasts/episode-1.mp3"
		)
		assert merged["duration_seconds"] == 123.0
		assert merged["explicit"] is True
		assert merged["publish_date"] == "2026-01-15"

	def test_passed_in_values_take_precedence(self):
		from src.tasks.platform_distribution import _merge_episode_metadata

		merged = _merge_episode_metadata(
			_episode(),
			{"title": "Override", "audio_url": "https://cdn.example.com/a.mp3"},
		)

		assert merged["title"] == "Override"
		assert merged["audio_url"] == "https://cdn.example.com/a.mp3"
		# Non-overridden DB values are retained.
		assert merged["description"] == "A great episode"

	def test_omits_none_db_values(self):
		from src.tasks.platform_distribution import _merge_episode_metadata

		episode = _episode(
			episode_metadata={"title": "T"}, duration_seconds=None, s3_url=None
		)
		merged = _merge_episode_metadata(episode, {})

		assert merged["title"] == "T"
		assert "audio_url" not in merged
		assert "duration_seconds" not in merged
		# explicit defaults to False (a real value, so it is kept).
		assert merged["explicit"] is False

	def test_handles_empty_episode_metadata(self):
		from src.tasks.platform_distribution import _merge_episode_metadata

		episode = _episode(episode_metadata=None)
		merged = _merge_episode_metadata(episode, {})

		assert "title" not in merged
		assert merged["audio_url"].endswith(".mp3")


class TestDistributeTaskPopulatesMetadata:
	"""The task loads the Episode and forwards real metadata to the platform."""

	def test_task_populates_metadata_from_episode(self):
		from src.tasks.platform_distribution import distribute_to_platform_task

		episode = _episode()

		# Mock the sync DB session so db.get(Episode, ...) returns our episode.
		mock_session = MagicMock()
		mock_session.get.return_value = episode
		mock_session.__enter__ = MagicMock(return_value=mock_session)
		mock_session.__exit__ = MagicMock(return_value=False)

		captured = {}

		def _fake_spotify(episode_id, config, metadata, task):
			captured["metadata"] = metadata
			return {
				"status": "success",
				"platform": "spotify",
				"platform_episode_id": "sp_1",
				"platform_url": "https://open.spotify.com/episode/sp_1",
				"error": None,
			}

		with patch(
			"src.tasks.platform_distribution.SyncSessionLocal",
			return_value=mock_session,
		), patch(
			"src.tasks.platform_distribution._decrypt_platform_config",
			side_effect=lambda cfg, plat: cfg,
		), patch(
			"src.tasks.platform_distribution._distribute_to_spotify",
			side_effect=_fake_spotify,
		):
			distribute_to_platform_task.request.update(id="test-task")
			with patch.object(distribute_to_platform_task, "update_state", MagicMock()):
				result = distribute_to_platform_task.run(
					episode_id="00000000-0000-0000-0000-000000000001",
					platform="spotify",
					platform_config={"show_id": "show1", "oauth_tokens": {}},
					episode_metadata={},  # workflow passes empty — task must populate
				)

		assert result["status"] == "success"
		# The platform received non-empty metadata sourced from the Episode row.
		assert captured["metadata"]["title"] == "My Episode"
		assert captured["metadata"]["description"] == "A great episode"
		assert captured["metadata"]["audio_url"].endswith(".mp3")

	def test_task_does_not_publish_without_uploaded_audio(self):
		"""No s3_url (upload failed or not committed) must never publish.

		The task retries until its budget is exhausted, then fails — it must not
		call the platform service with a non-existent audio URL (issue #211).
		"""
		from src.tasks.platform_distribution import distribute_to_platform_task

		# Episode exists but has no s3_url yet (e.g. upload not committed / failed).
		episode = _episode(s3_url=None)
		session = MagicMock()
		session.get.return_value = episode
		session.__enter__ = MagicMock(return_value=session)
		session.__exit__ = MagicMock(return_value=False)

		webhook = MagicMock()

		with patch(
			"src.tasks.platform_distribution.SyncSessionLocal", return_value=session,
		), patch(
			"src.tasks.platform_distribution._decrypt_platform_config",
			side_effect=lambda cfg, plat: cfg,
		), patch(
			"src.tasks.platform_distribution._distribute_via_webhook", webhook,
		), patch.object(
			distribute_to_platform_task, "update_state", MagicMock(),
		), patch.object(
			distribute_to_platform_task, "retry",
			side_effect=distribute_to_platform_task.MaxRetriesExceededError(),
		) as mock_retry:
			distribute_to_platform_task.request.update(id="test-task-2", retries=5)
			result = distribute_to_platform_task.run(
				episode_id="00000000-0000-0000-0000-000000000002",
				platform="webhook",
				platform_config={"url": "https://hook.example.com/x"},
				episode_metadata={},
			)

		# Missing audio → retried (then exhausted → failed); never published.
		mock_retry.assert_called()
		assert result["status"] == "failed"
		webhook.assert_not_called()
