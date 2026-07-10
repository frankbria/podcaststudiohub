"""
Apple Podcasts Connect API client for episode distribution.

Provides a synchronous HTTP client suitable for use in Celery tasks.
Raises typed exceptions to enable selective retry logic:
- AppleAuthError (extends ValueError): permanent, do not retry
- AppleAPIError: transient, retry eligible
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

APPLE_API_BASE = "https://api.podcastsconnect.apple.com/v1"


class AppleAuthError(ValueError):
	"""
	Raised when Apple Podcasts authentication fails (HTTP 401/403).

	Extends ValueError so that should_retry_exception() treats this as
	a permanent error and does not schedule a retry.
	"""
	pass


class AppleAPIError(Exception):
	"""
	Raised for transient Apple Podcasts API errors (HTTP 429, 5xx) and
	network failures.  should_retry_exception() will schedule a retry.
	"""
	pass


class ApplePodcastsService:
	"""
	Thin synchronous client for the Apple Podcasts Connect API.

	Designed for use inside Celery tasks where async I/O is not available.
	Uses httpx in synchronous mode.

	Apple Podcasts Connect API uses a JSON:API (JSONAPI) envelope format.
	Requests are authenticated with a Bearer API key.
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
		api_key: str,
		metadata: Dict[str, Any],
		idempotency_key: Optional[str] = None,
	) -> Dict[str, Any]:
		"""
		Publish a podcast episode to Apple Podcasts Connect.

		Submits episode metadata and audio URL to the Apple Podcasts
		Connect API using the JSONAPI request format.

		Args:
			show_id: Apple Podcasts show identifier (from DistributionTarget.config.show_id)
			api_key: Decrypted Apple Podcasts Connect API key
			metadata: Episode metadata dict.  Recognised keys:
				- title (str): Episode title
				- description (str): Episode description
				- audio_url (str): Publicly accessible audio file URL
				- publish_date (str): ISO-8601 datetime string
				- explicit (bool): Whether episode contains explicit content
			idempotency_key: Stable token sent as an ``Idempotency-Key`` header
				so a retried publish deduplicates server-side (issue #312)

		Returns:
			Dict with keys:
				- episode_id (str): Apple Podcasts episode identifier
				- platform_url (str | None): Public episode URL on Apple Podcasts
					(None if API did not return a URL; will be known after Apple processes)

		Raises:
			AppleAuthError: Credentials invalid (HTTP 401/403)
			AppleAPIError: Rate limited (429), server error (5xx), or network error
			ValueError: Missing required configuration
		"""
		if not show_id:
			raise ValueError("Apple Podcasts show_id is required to publish an episode")
		if not api_key:
			raise ValueError("Apple Podcasts api_key is required to publish an episode")

		url = f"{APPLE_API_BASE}/episodes"
		headers = {
			"Authorization": f"Bearer {api_key}",
			"Content-Type": "application/json",
		}
		if idempotency_key:
			headers["Idempotency-Key"] = idempotency_key

		publish_date = metadata.get(
			"publish_date",
			datetime.now(timezone.utc).isoformat(),
		)

		# Build JSONAPI payload
		attributes: Dict[str, Any] = {
			"title": metadata.get("title", ""),
			"description": metadata.get("description", ""),
			"showId": show_id,
			"publishDate": publish_date,
			"explicit": metadata.get("explicit", False),
		}
		if metadata.get("audio_url"):
			attributes["audioUrl"] = metadata["audio_url"]

		payload = {
			"data": {
				"type": "episodes",
				"attributes": attributes,
			}
		}

		logger.info(
			"Publishing episode to Apple Podcasts show %s: %s",
			show_id,
			metadata.get("title", ""),
		)

		try:
			with httpx.Client(timeout=self.timeout) as client:
				response = client.post(url, json=payload, headers=headers)
				self._handle_response(response, "publish_episode")
				data = response.json()
		except (httpx.ConnectError, httpx.TimeoutException) as exc:
			raise AppleAPIError(
				f"Network error connecting to Apple Podcasts: {exc}"
			) from exc

		# Parse JSONAPI response
		episode_data = data.get("data", {})
		episode_id = episode_data.get("id", "")
		response_attrs = episode_data.get("attributes", {})
		platform_url: Optional[str] = response_attrs.get("websiteUrl")
		if not platform_url and episode_id:
			platform_url = (
				f"https://podcasts.apple.com/podcast/id{show_id}?i={episode_id}"
			)

		logger.info("Apple Podcasts episode published successfully: %s", episode_id)
		return {
			"episode_id": episode_id,
			"platform_url": platform_url,
		}

	def _handle_response(self, response: httpx.Response, operation: str) -> None:
		"""
		Inspect an httpx response and raise a typed exception on failure.

		Args:
			response: The httpx.Response to inspect
			operation: Short label used in error messages

		Raises:
			AppleAuthError: HTTP 401 or 403
			AppleAPIError: HTTP 429 or 5xx
		"""
		status = response.status_code

		if status in (401, 403):
			logger.warning(
				"Apple Podcasts auth error during %s: HTTP %d", operation, status
			)
			raise AppleAuthError(
				f"Apple Podcasts authentication failed during {operation}: HTTP {status}. "
				"Please verify your API key."
			)

		if status == 429:
			retry_after = response.headers.get("Retry-After", "60")
			raise AppleAPIError(
				f"Apple Podcasts rate limited during {operation}. "
				f"Retry after {retry_after}s."
			)

		if status >= 500:
			raise AppleAPIError(
				f"Apple Podcasts server error during {operation}: HTTP {status}"
			)

		# Raise for any other 4xx we didn't handle explicitly
		response.raise_for_status()
