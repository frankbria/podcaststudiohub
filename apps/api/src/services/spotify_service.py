"""
Spotify for Podcasters API client for episode distribution.

Provides a synchronous HTTP client suitable for use in Celery tasks.
Raises typed exceptions to enable selective retry logic:
- SpotifyAuthError (extends ValueError): permanent, do not retry
- SpotifyAPIError: transient, retry eligible
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

SPOTIFY_API_BASE = "https://api.spotify.com/v1"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"


class SpotifyAuthError(ValueError):
	"""
	Raised when Spotify authentication fails (HTTP 401/403).

	Extends ValueError so that should_retry_exception() treats this as
	a permanent error and does not schedule a retry.
	"""
	pass


class SpotifyAPIError(Exception):
	"""
	Raised for transient Spotify API errors (HTTP 429, 5xx) and network
	failures.  should_retry_exception() will schedule a retry.
	"""
	pass


class SpotifyService:
	"""
	Thin synchronous client for the Spotify for Podcasters API.

	Designed for use inside Celery tasks where async I/O is not available.
	Uses httpx in synchronous mode.
	"""

	def __init__(self, timeout: float = 30.0):
		"""
		Args:
			timeout: HTTP request timeout in seconds.
		"""
		self.timeout = timeout

	def publish_episode(
		self,
		show_id: str,
		access_token: str,
		metadata: Dict[str, Any],
		idempotency_key: Optional[str] = None,
	) -> Dict[str, Any]:
		"""
		Publish a podcast episode to Spotify for Podcasters.

		Sends episode metadata and audio URL to the Spotify Web API.
		The show must already exist on Spotify for Podcasters.

		Args:
			show_id: Spotify show identifier (from DistributionTarget.config.show_id)
			access_token: Decrypted Spotify OAuth access token
			metadata: Episode metadata dict.  Recognised keys:
				- title (str): Episode title
				- description (str): Episode description
				- audio_url (str): Publicly accessible audio file URL
				- duration_seconds (float): Episode duration
				- publish_date (str): ISO-8601 date string (e.g. "2024-01-15")
				- explicit (bool): Whether episode contains explicit content
			idempotency_key: Stable token sent as an ``Idempotency-Key`` header
				so a retried publish deduplicates server-side (issue #312)

		Returns:
			Dict with keys:
				- episode_id (str): Spotify episode identifier
				- platform_url (str): Public episode URL on Spotify

		Raises:
			SpotifyAuthError: Credentials invalid or expired (HTTP 401/403)
			SpotifyAPIError: Rate limited (429), server error (5xx), or network error
			ValueError: Missing required configuration
		"""
		if not show_id:
			raise ValueError("Spotify show_id is required to publish an episode")
		if not access_token:
			raise ValueError("Spotify access_token is required to publish an episode")

		url = f"{SPOTIFY_API_BASE}/shows/{show_id}/episodes"
		headers = {
			"Authorization": f"Bearer {access_token}",
			"Content-Type": "application/json",
		}
		if idempotency_key:
			headers["Idempotency-Key"] = idempotency_key

		payload: Dict[str, Any] = {
			"name": metadata.get("title", ""),
			"description": metadata.get("description", ""),
			"explicit": metadata.get("explicit", False),
			"release_date": metadata.get(
				"publish_date",
				datetime.now(timezone.utc).strftime("%Y-%m-%d"),
			),
		}
		duration_seconds = metadata.get("duration_seconds")
		if duration_seconds is not None:
			payload["duration_ms"] = int(float(duration_seconds) * 1000)
		if metadata.get("audio_url"):
			# Spotify for Podcasters primarily ingests episodes through the show's
			# RSS feed; the catalog Web API exposes audio only as the read-only
			# `audio_preview_url`, which is not a valid field for submitting episode
			# audio. Send the audio under `audio_url` (the submission field) instead
			# of the read-only preview field. Direct API publishing remains
			# best-effort and subject to platform limitations (issue #211).
			payload["audio_url"] = metadata["audio_url"]

		logger.info(
			"Publishing episode to Spotify show %s: %s",
			show_id,
			metadata.get("title", ""),
		)

		try:
			with httpx.Client(timeout=self.timeout) as client:
				response = client.post(url, json=payload, headers=headers)
				self._handle_response(response, "publish_episode")
				data = response.json()
		except (httpx.ConnectError, httpx.TimeoutException) as exc:
			raise SpotifyAPIError(
				f"Network error connecting to Spotify: {exc}"
			) from exc

		episode_id = data.get("id", "")
		external_urls = data.get("external_urls", {})
		platform_url = external_urls.get("spotify") or (
			f"https://open.spotify.com/episode/{episode_id}" if episode_id else None
		)

		logger.info("Spotify episode published successfully: %s", episode_id)
		return {
			"episode_id": episode_id,
			"platform_url": platform_url,
		}

	def refresh_access_token(
		self,
		refresh_token: str,
		client_id: str,
		client_secret: str,
	) -> Dict[str, Any]:
		"""
		Refresh an expired Spotify OAuth access token.

		Uses the OAuth 2.0 refresh_token grant to obtain a new access token
		without requiring user interaction.

		Args:
			refresh_token: Decrypted Spotify OAuth refresh token
			client_id: Spotify application client ID (from settings)
			client_secret: Spotify application client secret (from settings)

		Returns:
			Token response dict with at minimum:
				- access_token (str): New access token
				- expires_in (int): TTL in seconds
				- token_type (str): Always "Bearer"
			May also contain refresh_token if Spotify issued a new one.

		Raises:
			SpotifyAuthError: Refresh token invalid/revoked (HTTP 400/401)
			SpotifyAPIError: Server error (5xx) or network failure
		"""
		if not refresh_token:
			raise ValueError("Spotify refresh_token is required")
		if not client_id or not client_secret:
			raise ValueError("Spotify client_id and client_secret are required for token refresh")

		logger.info("Refreshing Spotify access token")

		try:
			with httpx.Client(timeout=self.timeout) as client:
				response = client.post(
					SPOTIFY_TOKEN_URL,
					data={
						"grant_type": "refresh_token",
						"refresh_token": refresh_token,
					},
					auth=(client_id, client_secret),
					headers={"Content-Type": "application/x-www-form-urlencoded"},
				)
				self._handle_response(response, "refresh_token")
				return response.json()
		except (httpx.ConnectError, httpx.TimeoutException) as exc:
			raise SpotifyAPIError(
				f"Network error refreshing Spotify token: {exc}"
			) from exc

	def _handle_response(self, response: httpx.Response, operation: str) -> None:
		"""
		Inspect an httpx response and raise a typed exception on failure.

		Args:
			response: The httpx.Response to inspect
			operation: Short label used in error messages

		Raises:
			SpotifyAuthError: HTTP 401 or 403
			SpotifyAPIError: HTTP 429 or 5xx
		"""
		status = response.status_code

		if status in (401, 403):
			logger.warning(
				"Spotify auth error during %s: HTTP %d", operation, status
			)
			raise SpotifyAuthError(
				f"Spotify authentication failed during {operation}: HTTP {status}. "
				"Re-authorize the distribution target."
			)

		if status == 429:
			retry_after = response.headers.get("Retry-After", "60")
			raise SpotifyAPIError(
				f"Spotify rate limited during {operation}. "
				f"Retry after {retry_after}s."
			)

		if status >= 500:
			raise SpotifyAPIError(
				f"Spotify server error during {operation}: HTTP {status}"
			)

		# Raise for any other 4xx we didn't handle explicitly
		response.raise_for_status()
