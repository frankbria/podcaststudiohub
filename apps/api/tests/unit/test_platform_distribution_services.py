"""
Unit tests for Spotify and Apple Podcasts distribution services and the
updated platform_distribution Celery task.

All HTTP calls are mocked with httpx.Response objects so no real network
requests are made.  All tests are synchronous (no async required).
"""
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import httpx
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_httpx_response(
	status_code: int,
	json_body: dict | None = None,
	headers: dict | None = None,
) -> httpx.Response:
	"""
	Build a minimal httpx.Response for mocking.

	httpx.Response requires a request object; we attach a dummy one.
	"""
	import json as _json

	content = _json.dumps(json_body or {}).encode()
	response = httpx.Response(
		status_code=status_code,
		content=content,
		headers=headers or {},
		request=httpx.Request("POST", "https://example.com"),
	)
	return response


def _make_celery_retry_exc(task):
	return task.MaxRetriesExceededError()


def _direct_publish_enabled():
	"""Enable the experimental direct-publish path (issue #315) for one test."""
	from src.config import settings

	return patch.object(settings, "ENABLE_DIRECT_PLATFORM_PUBLISH", True)


# ===========================================================================
# SpotifyService tests
# ===========================================================================


class TestSpotifyServicePublishEpisode:
	"""Tests for SpotifyService.publish_episode()"""

	def test_success_returns_episode_id_and_url(self):
		"""Returns episode_id and platform_url on HTTP 200."""
		from src.services.spotify_service import SpotifyService

		body = {
			"id": "sp_ep_abc123",
			"external_urls": {"spotify": "https://open.spotify.com/episode/sp_ep_abc123"},
		}
		mock_response = _make_httpx_response(200, body)

		with patch("httpx.Client") as mock_client_cls:
			mock_client = MagicMock()
			mock_client.__enter__ = MagicMock(return_value=mock_client)
			mock_client.__exit__ = MagicMock(return_value=False)
			mock_client.post.return_value = mock_response
			mock_client_cls.return_value = mock_client

			svc = SpotifyService()
			result = svc.publish_episode(
				show_id="show123",
				access_token="token_abc",
				metadata={"title": "My Episode", "description": "Desc"},
			)

		assert result["episode_id"] == "sp_ep_abc123"
		assert result["platform_url"] == "https://open.spotify.com/episode/sp_ep_abc123"

	def test_sends_expected_request_url_headers_and_body(self):
		"""Asserts the exact outbound endpoint, auth header and JSON body (issue #315)."""
		from src.services.spotify_service import SpotifyService

		mock_response = _make_httpx_response(200, {"id": "ep1", "external_urls": {}})

		with patch("httpx.Client") as mock_client_cls:
			mock_client = MagicMock()
			mock_client.__enter__ = MagicMock(return_value=mock_client)
			mock_client.__exit__ = MagicMock(return_value=False)
			mock_client.post.return_value = mock_response
			mock_client_cls.return_value = mock_client

			SpotifyService().publish_episode(
				show_id="show123",
				access_token="token_abc",
				metadata={
					"title": "My Episode",
					"description": "Desc",
					"audio_url": "https://cdn.example.com/audio.mp3",
					"duration_seconds": 61.5,
					"publish_date": "2026-01-15",
					"explicit": True,
				},
				idempotency_key="ep-001:spotify",
			)

		args, kwargs = mock_client.post.call_args
		assert args[0] == "https://api.spotify.com/v1/shows/show123/episodes"
		assert kwargs["headers"]["Authorization"] == "Bearer token_abc"
		assert kwargs["headers"]["Content-Type"] == "application/json"
		assert kwargs["headers"]["Idempotency-Key"] == "ep-001:spotify"
		assert kwargs["json"] == {
			"name": "My Episode",
			"description": "Desc",
			"explicit": True,
			"release_date": "2026-01-15",
			"duration_ms": 61500,
			"audio_url": "https://cdn.example.com/audio.mp3",
		}

	def test_platform_url_fallback_when_external_urls_absent(self):
		"""Constructs fallback URL when external_urls missing from response."""
		from src.services.spotify_service import SpotifyService

		body = {"id": "ep_xyz"}
		mock_response = _make_httpx_response(200, body)

		with patch("httpx.Client") as mock_client_cls:
			mock_client = MagicMock()
			mock_client.__enter__ = MagicMock(return_value=mock_client)
			mock_client.__exit__ = MagicMock(return_value=False)
			mock_client.post.return_value = mock_response
			mock_client_cls.return_value = mock_client

			result = SpotifyService().publish_episode(
				show_id="show1", access_token="tok", metadata={}
			)

		assert result["platform_url"] == "https://open.spotify.com/episode/ep_xyz"

	def test_raises_spotify_auth_error_on_401(self):
		"""Raises SpotifyAuthError (permanent) on HTTP 401."""
		from src.services.spotify_service import SpotifyAuthError, SpotifyService

		mock_response = _make_httpx_response(401, {})

		with patch("httpx.Client") as mock_client_cls:
			mock_client = MagicMock()
			mock_client.__enter__ = MagicMock(return_value=mock_client)
			mock_client.__exit__ = MagicMock(return_value=False)
			mock_client.post.return_value = mock_response
			mock_client_cls.return_value = mock_client

			with pytest.raises(SpotifyAuthError):
				SpotifyService().publish_episode(
					show_id="show1", access_token="expired", metadata={}
				)

	def test_raises_spotify_auth_error_on_403(self):
		"""Raises SpotifyAuthError (permanent) on HTTP 403."""
		from src.services.spotify_service import SpotifyAuthError, SpotifyService

		mock_response = _make_httpx_response(403, {})

		with patch("httpx.Client") as mock_client_cls:
			mock_client = MagicMock()
			mock_client.__enter__ = MagicMock(return_value=mock_client)
			mock_client.__exit__ = MagicMock(return_value=False)
			mock_client.post.return_value = mock_response
			mock_client_cls.return_value = mock_client

			with pytest.raises(SpotifyAuthError):
				SpotifyService().publish_episode(
					show_id="show1", access_token="forbidden", metadata={}
				)

	def test_raises_spotify_api_error_on_429(self):
		"""Raises SpotifyAPIError (transient) on HTTP 429."""
		from src.services.spotify_service import SpotifyAPIError, SpotifyService

		mock_response = _make_httpx_response(429, {}, headers={"Retry-After": "30"})

		with patch("httpx.Client") as mock_client_cls:
			mock_client = MagicMock()
			mock_client.__enter__ = MagicMock(return_value=mock_client)
			mock_client.__exit__ = MagicMock(return_value=False)
			mock_client.post.return_value = mock_response
			mock_client_cls.return_value = mock_client

			with pytest.raises(SpotifyAPIError, match="rate limited"):
				SpotifyService().publish_episode(
					show_id="show1", access_token="tok", metadata={}
				)

	def test_raises_spotify_api_error_on_500(self):
		"""Raises SpotifyAPIError (transient) on HTTP 500."""
		from src.services.spotify_service import SpotifyAPIError, SpotifyService

		mock_response = _make_httpx_response(500, {})

		with patch("httpx.Client") as mock_client_cls:
			mock_client = MagicMock()
			mock_client.__enter__ = MagicMock(return_value=mock_client)
			mock_client.__exit__ = MagicMock(return_value=False)
			mock_client.post.return_value = mock_response
			mock_client_cls.return_value = mock_client

			with pytest.raises(SpotifyAPIError, match="server error"):
				SpotifyService().publish_episode(
					show_id="show1", access_token="tok", metadata={}
				)

	def test_raises_spotify_api_error_on_network_failure(self):
		"""Wraps httpx.ConnectError in SpotifyAPIError."""
		from src.services.spotify_service import SpotifyAPIError, SpotifyService

		with patch("httpx.Client") as mock_client_cls:
			mock_client = MagicMock()
			mock_client.__enter__ = MagicMock(return_value=mock_client)
			mock_client.__exit__ = MagicMock(return_value=False)
			mock_client.post.side_effect = httpx.ConnectError("connection refused")
			mock_client_cls.return_value = mock_client

			with pytest.raises(SpotifyAPIError, match="Network error"):
				SpotifyService().publish_episode(
					show_id="show1", access_token="tok", metadata={}
				)

	def test_raises_value_error_when_show_id_missing(self):
		"""Raises ValueError immediately when show_id is empty."""
		from src.services.spotify_service import SpotifyService

		with pytest.raises(ValueError, match="show_id"):
			SpotifyService().publish_episode(
				show_id="", access_token="tok", metadata={}
			)

	def test_raises_value_error_when_access_token_missing(self):
		"""Raises ValueError immediately when access_token is empty."""
		from src.services.spotify_service import SpotifyService

		with pytest.raises(ValueError, match="access_token"):
			SpotifyService().publish_episode(
				show_id="show1", access_token="", metadata={}
			)

	def test_auth_error_is_subclass_of_value_error(self):
		"""SpotifyAuthError must be a subclass of ValueError for retry suppression."""
		from src.services.spotify_service import SpotifyAuthError

		assert issubclass(SpotifyAuthError, ValueError)


class TestSpotifyServiceRefreshToken:
	"""Tests for SpotifyService.refresh_access_token()"""

	def test_success_returns_token_dict(self):
		"""Returns token dict on HTTP 200."""
		from src.services.spotify_service import SpotifyService

		body = {
			"access_token": "new_access_token",
			"token_type": "Bearer",
			"expires_in": 3600,
		}
		mock_response = _make_httpx_response(200, body)

		with patch("httpx.Client") as mock_client_cls:
			mock_client = MagicMock()
			mock_client.__enter__ = MagicMock(return_value=mock_client)
			mock_client.__exit__ = MagicMock(return_value=False)
			mock_client.post.return_value = mock_response
			mock_client_cls.return_value = mock_client

			result = SpotifyService().refresh_access_token(
				refresh_token="old_refresh",
				client_id="cid",
				client_secret="csec",
			)

		assert result["access_token"] == "new_access_token"
		assert result["expires_in"] == 3600

	def test_raises_spotify_auth_error_on_401(self):
		"""Raises SpotifyAuthError when refresh token is invalid."""
		from src.services.spotify_service import SpotifyAuthError, SpotifyService

		mock_response = _make_httpx_response(401, {})

		with patch("httpx.Client") as mock_client_cls:
			mock_client = MagicMock()
			mock_client.__enter__ = MagicMock(return_value=mock_client)
			mock_client.__exit__ = MagicMock(return_value=False)
			mock_client.post.return_value = mock_response
			mock_client_cls.return_value = mock_client

			with pytest.raises(SpotifyAuthError):
				SpotifyService().refresh_access_token(
					refresh_token="revoked", client_id="c", client_secret="s"
				)

	def test_raises_spotify_api_error_on_server_error(self):
		"""Raises SpotifyAPIError on HTTP 500."""
		from src.services.spotify_service import SpotifyAPIError, SpotifyService

		mock_response = _make_httpx_response(500, {})

		with patch("httpx.Client") as mock_client_cls:
			mock_client = MagicMock()
			mock_client.__enter__ = MagicMock(return_value=mock_client)
			mock_client.__exit__ = MagicMock(return_value=False)
			mock_client.post.return_value = mock_response
			mock_client_cls.return_value = mock_client

			with pytest.raises(SpotifyAPIError):
				SpotifyService().refresh_access_token(
					refresh_token="r", client_id="c", client_secret="s"
				)

	def test_raises_value_error_when_credentials_missing(self):
		"""Raises ValueError when client_id or client_secret are empty."""
		from src.services.spotify_service import SpotifyService

		with pytest.raises(ValueError, match="client_id"):
			SpotifyService().refresh_access_token(
				refresh_token="r", client_id="", client_secret="s"
			)


# ===========================================================================
# ApplePodcastsService tests
# ===========================================================================


class TestApplePodcastsServicePublishEpisode:
	"""Tests for ApplePodcastsService.publish_episode()"""

	def test_success_returns_episode_id_and_url(self):
		"""Returns episode_id and platform_url on HTTP 201."""
		from src.services.apple_podcasts_service import ApplePodcastsService

		body = {
			"data": {
				"id": "apple_ep_001",
				"type": "episodes",
				"attributes": {
					"websiteUrl": "https://podcasts.apple.com/podcast/id123?i=apple_ep_001",
					"title": "Test Episode",
				},
			}
		}
		mock_response = _make_httpx_response(201, body)

		with patch("httpx.Client") as mock_client_cls:
			mock_client = MagicMock()
			mock_client.__enter__ = MagicMock(return_value=mock_client)
			mock_client.__exit__ = MagicMock(return_value=False)
			mock_client.post.return_value = mock_response
			mock_client_cls.return_value = mock_client

			result = ApplePodcastsService().publish_episode(
				show_id="show123",
				api_key="ak_test",
				metadata={"title": "Test Episode"},
			)

		assert result["episode_id"] == "apple_ep_001"
		assert "apple_ep_001" in result["platform_url"]

	def test_sends_expected_request_url_headers_and_body(self):
		"""Asserts the exact outbound endpoint, auth header and JSONAPI body (issue #315)."""
		from src.services.apple_podcasts_service import ApplePodcastsService

		body = {"data": {"id": "ep1", "type": "episodes", "attributes": {}}}
		mock_response = _make_httpx_response(201, body)

		with patch("httpx.Client") as mock_client_cls:
			mock_client = MagicMock()
			mock_client.__enter__ = MagicMock(return_value=mock_client)
			mock_client.__exit__ = MagicMock(return_value=False)
			mock_client.post.return_value = mock_response
			mock_client_cls.return_value = mock_client

			ApplePodcastsService().publish_episode(
				show_id="apple_show_1",
				api_key="ak_test",
				metadata={
					"title": "My Episode",
					"description": "Desc",
					"audio_url": "https://cdn.example.com/audio.mp3",
					"publish_date": "2026-01-15T00:00:00+00:00",
					"explicit": False,
				},
				idempotency_key="ep-002:apple_podcasts",
			)

		args, kwargs = mock_client.post.call_args
		assert args[0] == "https://api.podcastsconnect.apple.com/v1/episodes"
		assert kwargs["headers"]["Authorization"] == "Bearer ak_test"
		assert kwargs["headers"]["Content-Type"] == "application/json"
		assert kwargs["headers"]["Idempotency-Key"] == "ep-002:apple_podcasts"
		assert kwargs["json"] == {
			"data": {
				"type": "episodes",
				"attributes": {
					"title": "My Episode",
					"description": "Desc",
					"showId": "apple_show_1",
					"publishDate": "2026-01-15T00:00:00+00:00",
					"explicit": False,
					"audioUrl": "https://cdn.example.com/audio.mp3",
				},
			}
		}

	def test_platform_url_fallback_when_website_url_absent(self):
		"""Constructs fallback URL from show_id and episode_id when websiteUrl absent."""
		from src.services.apple_podcasts_service import ApplePodcastsService

		body = {"data": {"id": "ep_xyz", "type": "episodes", "attributes": {}}}
		mock_response = _make_httpx_response(201, body)

		with patch("httpx.Client") as mock_client_cls:
			mock_client = MagicMock()
			mock_client.__enter__ = MagicMock(return_value=mock_client)
			mock_client.__exit__ = MagicMock(return_value=False)
			mock_client.post.return_value = mock_response
			mock_client_cls.return_value = mock_client

			result = ApplePodcastsService().publish_episode(
				show_id="show456", api_key="ak", metadata={}
			)

		assert "show456" in result["platform_url"]
		assert "ep_xyz" in result["platform_url"]

	def test_raises_apple_auth_error_on_401(self):
		"""Raises AppleAuthError (permanent) on HTTP 401."""
		from src.services.apple_podcasts_service import AppleAuthError, ApplePodcastsService

		mock_response = _make_httpx_response(401, {})

		with patch("httpx.Client") as mock_client_cls:
			mock_client = MagicMock()
			mock_client.__enter__ = MagicMock(return_value=mock_client)
			mock_client.__exit__ = MagicMock(return_value=False)
			mock_client.post.return_value = mock_response
			mock_client_cls.return_value = mock_client

			with pytest.raises(AppleAuthError):
				ApplePodcastsService().publish_episode(
					show_id="s", api_key="bad_key", metadata={}
				)

	def test_raises_apple_auth_error_on_403(self):
		"""Raises AppleAuthError (permanent) on HTTP 403."""
		from src.services.apple_podcasts_service import AppleAuthError, ApplePodcastsService

		mock_response = _make_httpx_response(403, {})

		with patch("httpx.Client") as mock_client_cls:
			mock_client = MagicMock()
			mock_client.__enter__ = MagicMock(return_value=mock_client)
			mock_client.__exit__ = MagicMock(return_value=False)
			mock_client.post.return_value = mock_response
			mock_client_cls.return_value = mock_client

			with pytest.raises(AppleAuthError):
				ApplePodcastsService().publish_episode(
					show_id="s", api_key="forbidden", metadata={}
				)

	def test_raises_apple_api_error_on_429(self):
		"""Raises AppleAPIError (transient) on HTTP 429."""
		from src.services.apple_podcasts_service import AppleAPIError, ApplePodcastsService

		mock_response = _make_httpx_response(429, {}, headers={"Retry-After": "60"})

		with patch("httpx.Client") as mock_client_cls:
			mock_client = MagicMock()
			mock_client.__enter__ = MagicMock(return_value=mock_client)
			mock_client.__exit__ = MagicMock(return_value=False)
			mock_client.post.return_value = mock_response
			mock_client_cls.return_value = mock_client

			with pytest.raises(AppleAPIError, match="rate limited"):
				ApplePodcastsService().publish_episode(
					show_id="s", api_key="k", metadata={}
				)

	def test_raises_apple_api_error_on_500(self):
		"""Raises AppleAPIError (transient) on HTTP 500."""
		from src.services.apple_podcasts_service import AppleAPIError, ApplePodcastsService

		mock_response = _make_httpx_response(500, {})

		with patch("httpx.Client") as mock_client_cls:
			mock_client = MagicMock()
			mock_client.__enter__ = MagicMock(return_value=mock_client)
			mock_client.__exit__ = MagicMock(return_value=False)
			mock_client.post.return_value = mock_response
			mock_client_cls.return_value = mock_client

			with pytest.raises(AppleAPIError, match="server error"):
				ApplePodcastsService().publish_episode(
					show_id="s", api_key="k", metadata={}
				)

	def test_raises_apple_api_error_on_network_failure(self):
		"""Wraps httpx.ConnectError in AppleAPIError."""
		from src.services.apple_podcasts_service import AppleAPIError, ApplePodcastsService

		with patch("httpx.Client") as mock_client_cls:
			mock_client = MagicMock()
			mock_client.__enter__ = MagicMock(return_value=mock_client)
			mock_client.__exit__ = MagicMock(return_value=False)
			mock_client.post.side_effect = httpx.ConnectError("refused")
			mock_client_cls.return_value = mock_client

			with pytest.raises(AppleAPIError, match="Network error"):
				ApplePodcastsService().publish_episode(
					show_id="s", api_key="k", metadata={}
				)

	def test_raises_value_error_when_show_id_missing(self):
		"""Raises ValueError immediately when show_id is empty."""
		from src.services.apple_podcasts_service import ApplePodcastsService

		with pytest.raises(ValueError, match="show_id"):
			ApplePodcastsService().publish_episode(
				show_id="", api_key="k", metadata={}
			)

	def test_raises_value_error_when_api_key_missing(self):
		"""Raises ValueError immediately when api_key is empty."""
		from src.services.apple_podcasts_service import ApplePodcastsService

		with pytest.raises(ValueError, match="api_key"):
			ApplePodcastsService().publish_episode(
				show_id="s", api_key="", metadata={}
			)

	def test_auth_error_is_subclass_of_value_error(self):
		"""AppleAuthError must be a subclass of ValueError for retry suppression."""
		from src.services.apple_podcasts_service import AppleAuthError

		assert issubclass(AppleAuthError, ValueError)


# ===========================================================================
# _distribute_to_spotify task function tests
# ===========================================================================


class TestDistributeToSpotify:
	"""Tests for _distribute_to_spotify() in platform_distribution task."""

	def _invoke(self, config, metadata=None, mock_task=None):
		from src.tasks.platform_distribution import _distribute_to_spotify

		task = mock_task or MagicMock()
		task.update_state = MagicMock()
		return _distribute_to_spotify("ep-001", config, metadata or {}, task)

	def test_rss_default_returns_feed_url_without_publishing(self):
		"""Default (flag off): no publish_episode call; returns the RSS feed URL (issue #315)."""
		from src.services.spotify_service import SpotifyService

		config = {"show_id": "show1", "oauth_tokens": {"access_token": "tok"}}
		feed_url = "https://cdn.example.com/rss-feeds/proj-1/feed.xml"

		with patch.object(SpotifyService, "publish_episode") as mock_publish:
			result = self._invoke(config, metadata={"rss_feed_url": feed_url})

		mock_publish.assert_not_called()
		assert result == {
			"status": "success",
			"platform": "spotify",
			"method": "rss_feed",
			"platform_episode_id": None,
			"platform_url": feed_url,
			"rss_feed_url": feed_url,
			"error": None,
		}

	def test_rss_default_fails_clearly_without_feed_url(self):
		"""Default (flag off): missing RSS feed is a clear permanent failure, not fake success."""
		with pytest.raises(ValueError, match="RSS feed"):
			self._invoke(config={"show_id": "show1", "oauth_tokens": {"access_token": "tok"}})

	def test_rss_default_does_not_require_oauth_credentials(self):
		"""Default (flag off): RSS ingestion needs no OAuth token."""
		result = self._invoke(
			config={"show_id": "show1"},
			metadata={"rss_feed_url": "https://cdn.example.com/feed.xml"},
		)
		assert result["method"] == "rss_feed"

	def test_direct_publish_called_once_with_expected_args_when_enabled(self):
		"""Flag on: publish_episode called exactly once with show_id, metadata, idempotency key."""
		from src.services.spotify_service import SpotifyService

		config = {"show_id": "show1", "oauth_tokens": {"access_token": "tok"}}

		with _direct_publish_enabled(), patch.object(
			SpotifyService,
			"publish_episode",
			return_value={"episode_id": "e1", "platform_url": "https://open.spotify.com/episode/e1"},
		) as mock_publish:
			self._invoke(config, metadata={"title": "T"})

		mock_publish.assert_called_once_with(
			show_id="show1",
			access_token="tok",
			metadata={"title": "T"},
			idempotency_key="ep-001:spotify",
		)

	def test_success_returns_real_episode_id(self):
		"""Returns real episode_id from SpotifyService on success (direct path)."""
		from src.services.spotify_service import SpotifyService

		config = {
			"show_id": "show1",
			"oauth_tokens": {"access_token": "tok"},
		}

		with _direct_publish_enabled(), patch.object(
			SpotifyService,
			"publish_episode",
			return_value={"episode_id": "real_ep_id", "platform_url": "https://open.spotify.com/episode/real_ep_id"},
		):
			result = self._invoke(config)

		assert result["status"] == "success"
		assert result["platform_episode_id"] == "real_ep_id"
		assert result["platform_url"] == "https://open.spotify.com/episode/real_ep_id"
		assert result["error"] is None

	def test_no_placeholder_id_returned(self):
		"""Ensures the old 'spotify_placeholder_id' is never returned."""
		from src.services.spotify_service import SpotifyService

		config = {
			"show_id": "show1",
			"oauth_tokens": {"access_token": "tok"},
		}

		with _direct_publish_enabled(), patch.object(
			SpotifyService,
			"publish_episode",
			return_value={"episode_id": "real_id", "platform_url": "https://open.spotify.com/episode/real_id"},
		):
			result = self._invoke(config)

		assert result["platform_episode_id"] != "spotify_placeholder_id"

	def test_raises_value_error_when_show_id_missing(self):
		"""Raises ValueError when show_id absent from config."""
		with pytest.raises(ValueError, match="show_id"):
			self._invoke(config={"oauth_tokens": {"access_token": "tok"}})

	def test_raises_value_error_when_access_token_missing(self):
		"""Raises ValueError when access_token absent from config (direct path)."""
		with _direct_publish_enabled():
			with pytest.raises(ValueError, match="access token"):
				self._invoke(config={"show_id": "s", "oauth_tokens": {}})

	def test_refreshes_expired_token_before_publish(self):
		"""Calls refresh_access_token when expires_at is in the past."""
		from src.services.spotify_service import SpotifyService

		past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
		config = {
			"show_id": "show1",
			"oauth_tokens": {
				"access_token": "old_token",
				"refresh_token": "refresh_tok",
				"expires_at": past,
			},
		}

		with (
			patch("src.tasks.platform_distribution.settings") as mock_settings,
			patch.object(
				SpotifyService,
				"refresh_access_token",
				return_value={"access_token": "new_token", "expires_in": 3600},
			) as mock_refresh,
			patch.object(
				SpotifyService,
				"publish_episode",
				return_value={"episode_id": "ep1", "platform_url": "https://open.spotify.com/episode/ep1"},
			) as mock_publish,
		):
			mock_settings.ENABLE_DIRECT_PLATFORM_PUBLISH = True
			mock_settings.SPOTIFY_CLIENT_ID = "cid"
			mock_settings.SPOTIFY_CLIENT_SECRET = "csec"

			result = self._invoke(config)

		mock_refresh.assert_called_once_with(
			refresh_token="refresh_tok",
			client_id="cid",
			client_secret="csec",
		)
		# publish_episode must be called with the *new* token
		call_kwargs = mock_publish.call_args.kwargs
		assert call_kwargs["access_token"] == "new_token"
		assert result["status"] == "success"

	def test_skips_refresh_when_token_not_expired(self):
		"""Does not refresh token when expires_at is in the future."""
		from src.services.spotify_service import SpotifyService

		future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
		config = {
			"show_id": "show1",
			"oauth_tokens": {
				"access_token": "valid_token",
				"refresh_token": "refresh_tok",
				"expires_at": future,
			},
		}

		with (
			_direct_publish_enabled(),
			patch.object(SpotifyService, "refresh_access_token") as mock_refresh,
			patch.object(
				SpotifyService,
				"publish_episode",
				return_value={"episode_id": "ep1", "platform_url": "https://open.spotify.com/episode/ep1"},
			),
		):
			self._invoke(config)

		mock_refresh.assert_not_called()

	def test_raises_value_error_when_client_credentials_missing_for_refresh(self):
		"""Raises ValueError when SPOTIFY_CLIENT_ID/SECRET absent for token refresh."""
		past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
		config = {
			"show_id": "show1",
			"oauth_tokens": {
				"access_token": "old_token",
				"refresh_token": "refresh_tok",
				"expires_at": past,
			},
		}

		with patch("src.tasks.platform_distribution.settings") as mock_settings:
			mock_settings.ENABLE_DIRECT_PLATFORM_PUBLISH = True
			mock_settings.SPOTIFY_CLIENT_ID = None
			mock_settings.SPOTIFY_CLIENT_SECRET = None

			with pytest.raises(ValueError, match="SPOTIFY_CLIENT_ID"):
				self._invoke(config)


# ===========================================================================
# _distribute_to_apple task function tests
# ===========================================================================


class TestDistributeToApple:
	"""Tests for _distribute_to_apple() in platform_distribution task."""

	def _invoke(self, config, metadata=None, mock_task=None):
		from src.tasks.platform_distribution import _distribute_to_apple

		task = mock_task or MagicMock()
		task.update_state = MagicMock()
		return _distribute_to_apple("ep-002", config, metadata or {}, task)

	def test_rss_default_returns_feed_url_without_publishing(self):
		"""Default (flag off): no publish_episode call; returns the RSS feed URL (issue #315)."""
		from src.services.apple_podcasts_service import ApplePodcastsService

		config = {"show_id": "apple_show_1", "credentials": {"api_key": "ak_test"}}
		feed_url = "https://cdn.example.com/rss-feeds/proj-1/feed.xml"

		with patch.object(ApplePodcastsService, "publish_episode") as mock_publish:
			result = self._invoke(config, metadata={"rss_feed_url": feed_url})

		mock_publish.assert_not_called()
		assert result == {
			"status": "success",
			"platform": "apple_podcasts",
			"method": "rss_feed",
			"platform_episode_id": None,
			"platform_url": feed_url,
			"rss_feed_url": feed_url,
			"error": None,
		}

	def test_rss_default_fails_clearly_without_feed_url(self):
		"""Default (flag off): missing RSS feed is a clear permanent failure, not fake success."""
		with pytest.raises(ValueError, match="RSS feed"):
			self._invoke(config={"show_id": "s", "credentials": {"api_key": "k"}})

	def test_rss_default_does_not_require_api_credentials(self):
		"""Default (flag off): RSS ingestion needs no Apple API key."""
		result = self._invoke(
			config={"show_id": "s"},
			metadata={"rss_feed_url": "https://cdn.example.com/feed.xml"},
		)
		assert result["method"] == "rss_feed"

	def test_direct_publish_called_once_with_expected_args_when_enabled(self):
		"""Flag on: publish_episode called exactly once with show_id, metadata, idempotency key."""
		from src.services.apple_podcasts_service import ApplePodcastsService

		config = {"show_id": "apple_show_1", "credentials": {"api_key": "ak_test"}}

		with _direct_publish_enabled(), patch.object(
			ApplePodcastsService,
			"publish_episode",
			return_value={"episode_id": "e1", "platform_url": "https://podcasts.apple.com/podcast/id1?i=e1"},
		) as mock_publish:
			self._invoke(config, metadata={"title": "T"})

		mock_publish.assert_called_once_with(
			show_id="apple_show_1",
			api_key="ak_test",
			metadata={"title": "T"},
			idempotency_key="ep-002:apple_podcasts",
		)

	def test_success_returns_real_episode_id(self):
		"""Returns real episode_id from ApplePodcastsService on success (direct path)."""
		from src.services.apple_podcasts_service import ApplePodcastsService

		config = {
			"show_id": "apple_show_1",
			"credentials": {"api_key": "ak_test"},
		}

		with _direct_publish_enabled(), patch.object(
			ApplePodcastsService,
			"publish_episode",
			return_value={
				"episode_id": "real_apple_id",
				"platform_url": "https://podcasts.apple.com/podcast/id123?i=real_apple_id",
			},
		):
			result = self._invoke(config)

		assert result["status"] == "success"
		assert result["platform_episode_id"] == "real_apple_id"
		assert result["platform_url"] is not None
		assert result["error"] is None

	def test_no_placeholder_id_returned(self):
		"""Ensures the old 'apple_placeholder_id' is never returned."""
		from src.services.apple_podcasts_service import ApplePodcastsService

		config = {
			"show_id": "s",
			"credentials": {"api_key": "k"},
		}

		with _direct_publish_enabled(), patch.object(
			ApplePodcastsService,
			"publish_episode",
			return_value={"episode_id": "real_id", "platform_url": "https://podcasts.apple.com/podcast/id123?i=real_id"},
		):
			result = self._invoke(config)

		assert result["platform_episode_id"] != "apple_placeholder_id"

	def test_raises_value_error_when_show_id_missing(self):
		"""Raises ValueError when show_id absent from config."""
		with pytest.raises(ValueError, match="show_id"):
			self._invoke(config={"credentials": {"api_key": "k"}})

	def test_raises_value_error_when_api_key_missing(self):
		"""Raises ValueError when api_key absent from config (direct path)."""
		with _direct_publish_enabled():
			with pytest.raises(ValueError, match="API key"):
				self._invoke(config={"show_id": "s", "credentials": {}})

	def test_auth_error_propagates_from_service(self):
		"""AppleAuthError raised by service propagates out of the task function."""
		from src.services.apple_podcasts_service import AppleAuthError, ApplePodcastsService

		config = {
			"show_id": "s",
			"credentials": {"api_key": "bad_key"},
		}

		with _direct_publish_enabled(), patch.object(
			ApplePodcastsService,
			"publish_episode",
			side_effect=AppleAuthError("HTTP 401"),
		):
			with pytest.raises(AppleAuthError):
				self._invoke(config)

	def test_api_error_propagates_from_service(self):
		"""AppleAPIError raised by service propagates out of the task function."""
		from src.services.apple_podcasts_service import AppleAPIError, ApplePodcastsService

		config = {
			"show_id": "s",
			"credentials": {"api_key": "key"},
		}

		with _direct_publish_enabled(), patch.object(
			ApplePodcastsService,
			"publish_episode",
			side_effect=AppleAPIError("HTTP 500"),
		):
			with pytest.raises(AppleAPIError):
				self._invoke(config)


# ===========================================================================
# RSS feed URL resolution + injection into the distribution task (issue #315)
# ===========================================================================


class TestRssFeedUrlResolution:
	"""Tests for _rss_feed_url_for_project() and its wiring into the task."""

	def test_resolver_returns_public_url(self):
		from src.tasks.platform_distribution import _rss_feed_url_for_project

		feed = MagicMock()
		feed.public_url = "https://cdn.example.com/rss-feeds/proj-1/feed.xml"
		db = MagicMock()
		db.execute.return_value.scalar_one_or_none.return_value = feed

		assert (
			_rss_feed_url_for_project(db, "proj-1")
			== "https://cdn.example.com/rss-feeds/proj-1/feed.xml"
		)

	def test_resolver_returns_none_when_no_feed(self):
		from src.tasks.platform_distribution import _rss_feed_url_for_project

		db = MagicMock()
		db.execute.return_value.scalar_one_or_none.return_value = None

		assert _rss_feed_url_for_project(db, "proj-1") is None

	def test_resolver_returns_none_when_feed_not_yet_generated(self):
		"""A feed row mid-generation (public_url still NULL) must not count as a feed."""
		from src.tasks.platform_distribution import _rss_feed_url_for_project

		feed = MagicMock()
		feed.public_url = None
		db = MagicMock()
		db.execute.return_value.scalar_one_or_none.return_value = feed

		assert _rss_feed_url_for_project(db, "proj-1") is None

	@pytest.mark.parametrize(
		"platform,helper_name",
		[("spotify", "_distribute_to_spotify"), ("apple_podcasts", "_distribute_to_apple")],
	)
	def test_task_injects_feed_url_into_metadata(self, platform, helper_name):
		"""distribute_to_platform_task resolves the project's feed URL and passes it on."""
		import src.tasks.platform_distribution as pd

		episode_id = "11111111-2222-3333-4444-555555555555"
		episode = MagicMock()
		episode.generation_progress = {}
		episode.project_id = "proj-1"
		episode.episode_metadata = {"title": "T", "description": "D"}
		episode.duration_seconds = None
		episode.s3_url = "https://cdn.example.com/audio.mp3"

		captured = {}

		def fake_helper(eid, config, metadata, task):
			captured["metadata"] = metadata
			return {
				"status": "success",
				"platform": platform,
				"method": "rss_feed",
				"platform_episode_id": None,
				"platform_url": metadata.get("rss_feed_url"),
				"rss_feed_url": metadata.get("rss_feed_url"),
				"error": None,
			}

		with (
			patch.object(pd, "SyncSessionLocal") as mock_ssl,
			patch.object(
				pd, "_rss_feed_url_for_project", return_value="https://cdn.example.com/feed.xml"
			) as mock_resolver,
			patch.object(pd, helper_name, side_effect=fake_helper),
			patch("src.tasks.callbacks.record_platform_distribution", return_value=True),
			patch.object(pd.distribute_to_platform_task, "update_state"),
		):
			mock_ssl.return_value.__enter__.return_value.get.return_value = episode
			result = pd.distribute_to_platform_task(
				episode_id, platform, {"show_id": "s"}, {}
			)

		mock_resolver.assert_called_once()
		assert mock_resolver.call_args.args[1] == "proj-1"
		assert captured["metadata"]["rss_feed_url"] == "https://cdn.example.com/feed.xml"
		assert result["rss_feed_url"] == "https://cdn.example.com/feed.xml"


# ===========================================================================
# Retry classification sanity checks
# ===========================================================================


class TestRetryClassification:
	"""Verify that auth errors are classified as non-retryable by should_retry_exception."""

	def test_spotify_auth_error_not_retried(self):
		"""SpotifyAuthError must be classified as non-retryable."""
		from src.services.spotify_service import SpotifyAuthError
		from src.tasks.retry_utils import should_retry_exception

		assert should_retry_exception(SpotifyAuthError("bad token")) is False

	def test_apple_auth_error_not_retried(self):
		"""AppleAuthError must be classified as non-retryable."""
		from src.services.apple_podcasts_service import AppleAuthError
		from src.tasks.retry_utils import should_retry_exception

		assert should_retry_exception(AppleAuthError("bad key")) is False

	def test_spotify_api_error_is_retried(self):
		"""SpotifyAPIError must be classified as retryable."""
		from src.services.spotify_service import SpotifyAPIError
		from src.tasks.retry_utils import should_retry_exception

		assert should_retry_exception(SpotifyAPIError("server error")) is True

	def test_apple_api_error_is_retried(self):
		"""AppleAPIError must be classified as retryable."""
		from src.services.apple_podcasts_service import AppleAPIError
		from src.tasks.retry_utils import should_retry_exception

		assert should_retry_exception(AppleAPIError("server error")) is True


# ===========================================================================
# Webhook distribution — IP pinning (issue #234)
# ===========================================================================


class TestWebhookIPPinning:
	"""_distribute_via_webhook must connect via a session pinned to the
	guard-validated IP so the host cannot re-resolve to an internal address."""

	def _session_returning(self, response):
		"""Build a mock pinned-session context manager returning ``response``."""
		session = MagicMock()
		session.__enter__.return_value = session
		session.__exit__.return_value = False
		session.post.return_value = response
		session.get.return_value = response
		return session

	def test_webhook_post_uses_pinned_session(self):
		from src.tasks import platform_distribution

		ok = MagicMock()
		ok.raise_for_status = MagicMock()
		fake_session = self._session_returning(ok)
		task = MagicMock()

		# pinned_session is imported inside the function, so patch it at source.
		# IP-literal host resolves to itself offline -> validated public IP.
		with patch(
			"src.utils.pinned_fetch.pinned_session", return_value=fake_session
		) as mock_pinned:
			result = platform_distribution._distribute_via_webhook(
				episode_id="ep-1",
				config={"url": "https://93.184.216.34/hook", "method": "POST"},
				metadata={"title": "x"},
				task=task,
			)

		# Pinned to the validated IP literal, and that session did the POST.
		mock_pinned.assert_called_once_with("https://93.184.216.34/hook", "93.184.216.34")
		fake_session.post.assert_called_once()
		assert result["status"] == "success"
