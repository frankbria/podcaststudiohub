"""
Unit tests for distribution idempotency (issue #312).

A Celery redelivery of distribute_to_platform_task (acks_late, max_retries=5)
must not republish an episode: platform publishes carry a stable
``{episode_id}:{platform}`` Idempotency-Key, platforms already recorded
complete are skipped, and success is recorded transactionally in-task.

All HTTP and DB interactions are mocked.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx

EPISODE_ID = "00000000-0000-0000-0000-000000000001"


def _make_httpx_response(status_code: int, json_body: dict | None = None) -> httpx.Response:
	import json as _json

	return httpx.Response(
		status_code=status_code,
		content=_json.dumps(json_body or {}).encode(),
		request=httpx.Request("POST", "https://example.com"),
	)


def _mock_httpx_client(response: httpx.Response) -> MagicMock:
	client = MagicMock()
	client.__enter__ = MagicMock(return_value=client)
	client.__exit__ = MagicMock(return_value=False)
	client.post.return_value = response
	return client


def _episode(**overrides):
	data = {
		"episode_metadata": {"title": "T", "description": "D"},
		"duration_seconds": 10.0,
		"s3_url": "https://bucket.s3.amazonaws.com/e.mp3",
		"generation_progress": {},
		"project_id": "00000000-0000-0000-0000-0000000000aa",
	}
	data.update(overrides)
	return SimpleNamespace(**data)


def _mock_session(episode) -> MagicMock:
	session = MagicMock()
	session.get.return_value = episode
	session.__enter__ = MagicMock(return_value=session)
	session.__exit__ = MagicMock(return_value=False)
	return session


# ===========================================================================
# Service-level: Idempotency-Key header
# ===========================================================================


class TestSpotifyIdempotencyHeader:
	def test_key_sets_idempotency_header(self):
		from src.services.spotify_service import SpotifyService

		body = {"id": "sp_1", "external_urls": {"spotify": "https://open.spotify.com/episode/sp_1"}}
		client = _mock_httpx_client(_make_httpx_response(200, body))
		with patch("httpx.Client", return_value=client):
			SpotifyService().publish_episode(
				show_id="show1",
				access_token="tok",
				metadata={"title": "T"},
				idempotency_key=f"{EPISODE_ID}:spotify",
			)

		headers = client.post.call_args.kwargs["headers"]
		assert headers["Idempotency-Key"] == f"{EPISODE_ID}:spotify"

	def test_no_key_no_header(self):
		from src.services.spotify_service import SpotifyService

		body = {"id": "sp_1", "external_urls": {"spotify": "https://open.spotify.com/episode/sp_1"}}
		client = _mock_httpx_client(_make_httpx_response(200, body))
		with patch("httpx.Client", return_value=client):
			SpotifyService().publish_episode(
				show_id="show1", access_token="tok", metadata={"title": "T"}
			)

		headers = client.post.call_args.kwargs["headers"]
		assert "Idempotency-Key" not in headers


class TestAppleIdempotencyHeader:
	def test_key_sets_idempotency_header(self):
		from src.services.apple_podcasts_service import ApplePodcastsService

		body = {"data": {"id": "ap_1", "attributes": {}}}
		client = _mock_httpx_client(_make_httpx_response(201, body))
		with patch("httpx.Client", return_value=client):
			ApplePodcastsService().publish_episode(
				show_id="show1",
				api_key="key",
				metadata={"title": "T"},
				idempotency_key=f"{EPISODE_ID}:apple_podcasts",
			)

		headers = client.post.call_args.kwargs["headers"]
		assert headers["Idempotency-Key"] == f"{EPISODE_ID}:apple_podcasts"

	def test_no_key_no_header(self):
		from src.services.apple_podcasts_service import ApplePodcastsService

		body = {"data": {"id": "ap_1", "attributes": {}}}
		client = _mock_httpx_client(_make_httpx_response(201, body))
		with patch("httpx.Client", return_value=client):
			ApplePodcastsService().publish_episode(
				show_id="show1", api_key="key", metadata={"title": "T"}
			)

		headers = client.post.call_args.kwargs["headers"]
		assert "Idempotency-Key" not in headers


# ===========================================================================
# Helper-level: key derivation and forwarding
# ===========================================================================


class TestHelpersForwardIdempotencyKey:
	def test_spotify_helper_forwards_key(self):
		from src.config import settings
		from src.tasks.platform_distribution import _distribute_to_spotify

		service = MagicMock()
		service.publish_episode.return_value = {
			"episode_id": "sp_1",
			"platform_url": "https://open.spotify.com/episode/sp_1",
		}
		with patch.object(
			settings, "ENABLE_DIRECT_PLATFORM_PUBLISH", True
		), patch("src.services.spotify_service.SpotifyService", return_value=service):
			_distribute_to_spotify(
				EPISODE_ID,
				{"show_id": "show1", "oauth_tokens": {"access_token": "tok"}},
				{"title": "T"},
				MagicMock(),
			)

		kwargs = service.publish_episode.call_args.kwargs
		assert kwargs["idempotency_key"] == f"{EPISODE_ID}:spotify"

	def test_apple_helper_forwards_key(self):
		from src.config import settings
		from src.tasks.platform_distribution import _distribute_to_apple

		service = MagicMock()
		service.publish_episode.return_value = {
			"episode_id": "ap_1",
			"platform_url": None,
		}
		with patch.object(
			settings, "ENABLE_DIRECT_PLATFORM_PUBLISH", True
		), patch(
			"src.services.apple_podcasts_service.ApplePodcastsService",
			return_value=service,
		):
			_distribute_to_apple(
				EPISODE_ID,
				{"show_id": "show1", "credentials": {"api_key": "key"}},
				{"title": "T"},
				MagicMock(),
			)

		kwargs = service.publish_episode.call_args.kwargs
		assert kwargs["idempotency_key"] == f"{EPISODE_ID}:apple_podcasts"

	def test_webhook_includes_key_in_header_and_payload(self):
		from src.tasks.platform_distribution import _distribute_via_webhook

		session = MagicMock()
		session.__enter__ = MagicMock(return_value=session)
		session.__exit__ = MagicMock(return_value=False)
		response = MagicMock()
		response.raise_for_status.return_value = None
		session.post.return_value = response

		with patch(
			"src.utils.ssrf.validate_public_url", return_value=("1.2.3.4", 443)
		), patch("src.utils.pinned_fetch.pinned_session", return_value=session):
			_distribute_via_webhook(
				EPISODE_ID,
				{"url": "https://hooks.example.com/x", "method": "POST"},
				{"title": "T"},
				MagicMock(),
			)

		kwargs = session.post.call_args.kwargs
		assert kwargs["headers"]["Idempotency-Key"] == f"{EPISODE_ID}:webhook"
		assert kwargs["json"]["idempotency_key"] == f"{EPISODE_ID}:webhook"

	def test_webhook_get_method_carries_key(self):
		from src.tasks.platform_distribution import _distribute_via_webhook

		session = MagicMock()
		session.__enter__ = MagicMock(return_value=session)
		session.__exit__ = MagicMock(return_value=False)
		response = MagicMock()
		response.raise_for_status.return_value = None
		session.get.return_value = response

		with patch(
			"src.utils.ssrf.validate_public_url", return_value=("1.2.3.4", 443)
		), patch("src.utils.pinned_fetch.pinned_session", return_value=session):
			_distribute_via_webhook(
				EPISODE_ID,
				{"url": "https://hooks.example.com/x", "method": "GET"},
				{"title": "T"},
				MagicMock(),
			)

		kwargs = session.get.call_args.kwargs
		assert kwargs["headers"]["Idempotency-Key"] == f"{EPISODE_ID}:webhook"
		assert kwargs["params"]["idempotency_key"] == f"{EPISODE_ID}:webhook"


# ===========================================================================
# Task-level: pre-publish skip of already-complete platforms
# ===========================================================================


class TestPrePublishSkip:
	def test_completed_platform_short_circuits(self):
		from src.tasks.platform_distribution import distribute_to_platform_task

		episode = _episode(
			generation_progress={
				"distribution": {
					"spotify": {
						"status": "complete",
						"platform_episode_id": "sp_prior",
						"platform_url": "https://open.spotify.com/episode/sp_prior",
						"distributed_at": "2026-07-01T00:00:00+00:00",
					}
				}
			}
		)
		session = _mock_session(episode)
		spotify = MagicMock()

		with patch(
			"src.tasks.platform_distribution.SyncSessionLocal", return_value=session
		), patch(
			"src.tasks.platform_distribution._decrypt_platform_config",
			side_effect=lambda cfg, plat: cfg,
		), patch(
			"src.tasks.platform_distribution._distribute_to_spotify", spotify
		):
			distribute_to_platform_task.request.update(id="t-skip")
			with patch.object(distribute_to_platform_task, "update_state", MagicMock()):
				result = distribute_to_platform_task.run(
					episode_id=EPISODE_ID,
					platform="spotify",
					platform_config={"show_id": "show1", "oauth_tokens": {}},
					episode_metadata={},
				)

		spotify.assert_not_called()
		assert result["status"] == "success"
		assert result["platform_episode_id"] == "sp_prior"
		assert result["platform_url"] == "https://open.spotify.com/episode/sp_prior"

	def test_incomplete_platform_still_publishes(self):
		from src.tasks.platform_distribution import distribute_to_platform_task

		episode = _episode(
			generation_progress={"distribution": {"spotify": {"status": "failed"}}}
		)
		session = _mock_session(episode)
		success = {
			"status": "success",
			"platform": "spotify",
			"platform_episode_id": "sp_new",
			"platform_url": "https://open.spotify.com/episode/sp_new",
			"error": None,
		}
		spotify = MagicMock(return_value=success)

		with patch(
			"src.tasks.platform_distribution.SyncSessionLocal", return_value=session
		), patch(
			"src.tasks.platform_distribution._decrypt_platform_config",
			side_effect=lambda cfg, plat: cfg,
		), patch(
			"src.tasks.platform_distribution._distribute_to_spotify", spotify
		), patch(
			"src.tasks.callbacks.record_platform_distribution", MagicMock()
		):
			distribute_to_platform_task.request.update(id="t-pub")
			with patch.object(distribute_to_platform_task, "update_state", MagicMock()):
				result = distribute_to_platform_task.run(
					episode_id=EPISODE_ID,
					platform="spotify",
					platform_config={"show_id": "show1", "oauth_tokens": {}},
					episode_metadata={},
				)

		spotify.assert_called_once()
		assert result["platform_episode_id"] == "sp_new"


# ===========================================================================
# Task-level: transactional success recording
# ===========================================================================


class TestInTaskSuccessRecording:
	def test_success_recorded_in_task(self):
		from src.tasks.platform_distribution import distribute_to_platform_task

		episode = _episode()
		session = _mock_session(episode)
		success = {
			"status": "success",
			"platform": "spotify",
			"platform_episode_id": "sp_1",
			"platform_url": "https://open.spotify.com/episode/sp_1",
			"error": None,
		}
		record = MagicMock()

		with patch(
			"src.tasks.platform_distribution.SyncSessionLocal", return_value=session
		), patch(
			"src.tasks.platform_distribution._decrypt_platform_config",
			side_effect=lambda cfg, plat: cfg,
		), patch(
			"src.tasks.platform_distribution._distribute_to_spotify",
			MagicMock(return_value=success),
		), patch(
			"src.tasks.callbacks.record_platform_distribution", record
		):
			distribute_to_platform_task.request.update(id="t-rec")
			with patch.object(distribute_to_platform_task, "update_state", MagicMock()):
				result = distribute_to_platform_task.run(
					episode_id=EPISODE_ID,
					platform="spotify",
					platform_config={"show_id": "show1", "oauth_tokens": {}},
					episode_metadata={},
				)

		record.assert_called_once_with(EPISODE_ID, "spotify", success)
		assert result == success

	def test_record_failure_does_not_fail_task(self):
		"""A DB error while recording must not retry (and thus republish)."""
		from src.tasks.platform_distribution import distribute_to_platform_task

		episode = _episode()
		session = _mock_session(episode)
		success = {
			"status": "success",
			"platform": "spotify",
			"platform_episode_id": "sp_1",
			"platform_url": "https://open.spotify.com/episode/sp_1",
			"error": None,
		}

		with patch(
			"src.tasks.platform_distribution.SyncSessionLocal", return_value=session
		), patch(
			"src.tasks.platform_distribution._decrypt_platform_config",
			side_effect=lambda cfg, plat: cfg,
		), patch(
			"src.tasks.platform_distribution._distribute_to_spotify",
			MagicMock(return_value=success),
		), patch(
			"src.tasks.callbacks.record_platform_distribution",
			MagicMock(side_effect=RuntimeError("db down")),
		):
			distribute_to_platform_task.request.update(id="t-recfail")
			with patch.object(distribute_to_platform_task, "update_state", MagicMock()):
				result = distribute_to_platform_task.run(
					episode_id=EPISODE_ID,
					platform="spotify",
					platform_config={"show_id": "show1", "oauth_tokens": {}},
					episode_metadata={},
				)

		assert result["status"] == "success"


# ===========================================================================
# record_platform_distribution (shared with on_distribution_complete)
# ===========================================================================


class TestRecordPlatformDistribution:
	def test_merges_complete_entry_and_commits(self):
		from src.tasks.callbacks import record_platform_distribution

		episode = SimpleNamespace(
			generation_progress={}, generation_status="distributing"
		)
		session = MagicMock()
		session.__enter__ = MagicMock(return_value=session)
		session.__exit__ = MagicMock(return_value=False)
		session.execute.return_value.scalar_one_or_none.return_value = episode

		result = {
			"status": "success",
			"platform": "spotify",
			"platform_episode_id": "sp_1",
			"platform_url": "https://open.spotify.com/episode/sp_1",
			"error": None,
		}
		with patch("src.tasks.callbacks.SyncSessionLocal", return_value=session):
			assert record_platform_distribution(EPISODE_ID, "spotify", result) is True

		entry = episode.generation_progress["distribution"]["spotify"]
		assert entry["status"] == "complete"
		assert entry["platform_episode_id"] == "sp_1"
		assert entry["platform_url"] == "https://open.spotify.com/episode/sp_1"
		assert "distributed_at" in entry
		session.commit.assert_called_once()

	def test_double_call_is_idempotent_re_merge(self):
		"""Second write (in-task then callback) re-merges an equivalent entry."""
		from src.tasks.callbacks import record_platform_distribution

		episode = SimpleNamespace(
			generation_progress={}, generation_status="distributing"
		)
		session = MagicMock()
		session.__enter__ = MagicMock(return_value=session)
		session.__exit__ = MagicMock(return_value=False)
		session.execute.return_value.scalar_one_or_none.return_value = episode

		result = {
			"status": "success",
			"platform": "spotify",
			"platform_episode_id": "sp_1",
			"platform_url": "https://open.spotify.com/episode/sp_1",
			"error": None,
		}
		with patch("src.tasks.callbacks.SyncSessionLocal", return_value=session):
			assert record_platform_distribution(EPISODE_ID, "spotify", result) is True
			first = dict(episode.generation_progress["distribution"]["spotify"])
			assert record_platform_distribution(EPISODE_ID, "spotify", result) is True
			second = episode.generation_progress["distribution"]["spotify"]

		# Identical shape and identifiers; only the timestamp may refresh.
		assert {k: v for k, v in first.items() if k != "distributed_at"} == {
			k: v for k, v in second.items() if k != "distributed_at"
		}
		assert second["status"] == "complete"

	def test_missing_episode_returns_false(self):
		from src.tasks.callbacks import record_platform_distribution

		session = MagicMock()
		session.__enter__ = MagicMock(return_value=session)
		session.__exit__ = MagicMock(return_value=False)
		session.execute.return_value.scalar_one_or_none.return_value = None

		with patch("src.tasks.callbacks.SyncSessionLocal", return_value=session):
			assert (
				record_platform_distribution(
					EPISODE_ID, "spotify", {"status": "success"}
				)
				is False
			)
		session.commit.assert_not_called()
