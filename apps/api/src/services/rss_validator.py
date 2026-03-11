"""
RSS Validation Service for podcast platform compliance.

Validates RSS feeds against Apple Podcasts, Spotify, and Google Podcasts
standards. Returns structured validation results for each platform.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import feedparser

logger = logging.getLogger(__name__)

# Valid iTunes categories per Apple Podcasts specification
VALID_ITUNES_CATEGORIES = {
	"Arts", "Business", "Comedy", "Education", "Fiction",
	"Government", "History", "Health & Fitness", "Kids & Family",
	"Leisure", "Music", "News", "Religion & Spirituality", "Science",
	"Society & Culture", "Sports", "Technology", "True Crime", "TV & Film",
}

# Audio MIME types supported by Spotify
SUPPORTED_AUDIO_TYPES = {
	"audio/mpeg", "audio/mp4", "audio/x-m4a", "audio/ogg",
	"audio/vorbis", "audio/aac", "audio/wav",
}


class RSSValidatorService:
	"""Validate RSS feeds against podcast platform standards."""

	def validate_feed(self, rss_xml: str) -> Dict[str, Any]:
		"""
		Validate RSS feed against Apple Podcasts, Spotify, and Google Podcasts standards.

		Args:
			rss_xml: RSS 2.0 XML string to validate

		Returns:
			Dict with per-platform validation results:
			{
				"last_validated_at": ISO timestamp,
				"apple_podcasts": {"valid": bool, "errors": [str]},
				"spotify": {"valid": bool, "errors": [str]},
				"google_podcasts": {"valid": bool, "errors": [str]}
			}
		"""
		try:
			feed = feedparser.parse(rss_xml)
		except Exception as e:
			logger.error(f"Failed to parse RSS feed: {e}")
			error_msg = f"Failed to parse RSS feed: {e}"
			return {
				"last_validated_at": datetime.now(timezone.utc).isoformat(),
				"apple_podcasts": {"valid": False, "errors": [error_msg]},
				"spotify": {"valid": False, "errors": [error_msg]},
				"google_podcasts": {"valid": False, "errors": [error_msg]},
			}

		apple_result = self._validate_apple_podcasts(feed)
		spotify_result = self._validate_spotify(feed)
		google_result = self._validate_google_podcasts(feed)

		return {
			"last_validated_at": datetime.now(timezone.utc).isoformat(),
			"apple_podcasts": apple_result,
			"spotify": spotify_result,
			"google_podcasts": google_result,
		}

	def _validate_apple_podcasts(self, feed: Any) -> Dict[str, Any]:
		"""
		Validate RSS feed against Apple Podcasts requirements.

		Checks required channel fields, iTunes namespace tags, and episode
		item requirements per Apple Podcasts specification.

		Args:
			feed: Parsed feedparser feed object

		Returns:
			{"valid": bool, "errors": [str]}
		"""
		errors: List[str] = []

		# Check feed-level parse errors
		if feed.bozo and feed.bozo_exception:
			errors.append(f"RSS parse error: {feed.bozo_exception}")

		channel = feed.feed

		# Required channel fields
		if not channel.get("title"):
			errors.append("Missing required channel field: title")
		if not channel.get("description") and not channel.get("summary"):
			errors.append("Missing required channel field: description")
		if not channel.get("link"):
			errors.append("Missing required channel field: link")
		if not channel.get("language"):
			errors.append("Missing required channel field: language")

		# iTunes namespace required fields
		# feedparser maps itunes:author to channel.author
		if not channel.get("author"):
			errors.append("Missing required iTunes field: itunes:author")

		# itunes:owner — feedparser 6 maps itunes:owner to publisher_detail
		# Fall back to author_detail if publisher_detail is absent
		owner = channel.get("publisher_detail") or channel.get("author_detail") or {}
		if not owner:
			errors.append("Missing required iTunes field: itunes:owner")
		else:
			if not owner.get("name"):
				errors.append("Missing itunes:owner/itunes:name")
			if not owner.get("email"):
				errors.append("Missing itunes:owner/itunes:email")

		# itunes:image — feedparser maps itunes:image href to channel.image.href
		image = channel.get("image") or {}
		if not image.get("href"):
			errors.append("Missing required iTunes field: itunes:image")

		# itunes:category — feedparser uses tags with scheme "http://www.itunes.com/..."
		categories = channel.get("tags") or []
		itunes_categories = [
			c.get("term", "") for c in categories
			if "itunes.com" in c.get("scheme", "")
		]
		if not itunes_categories:
			errors.append("Missing required iTunes field: itunes:category")

		# itunes:explicit — feedparser 6 maps "false" to None; only flag truly invalid values
		explicit = channel.get("itunes_explicit")
		if explicit is not None and str(explicit).lower() not in (
			"yes", "no", "clean", "true", "false", "none", ""
		):
			errors.append(
				f"Invalid itunes:explicit value '{explicit}'. Must be 'yes', 'no', or 'clean'"
			)

		# Episode item validation
		for i, entry in enumerate(feed.entries):
			ep_errors = self._validate_apple_episode(entry, i + 1)
			errors.extend(ep_errors)

		return {"valid": len(errors) == 0, "errors": errors}

	def _validate_apple_episode(self, entry: Any, episode_num: int) -> List[str]:
		"""
		Validate a single episode item for Apple Podcasts compliance.

		Args:
			entry: feedparser entry object
			episode_num: Episode position number (for error messages)

		Returns:
			List of error strings (empty if valid)
		"""
		errors: List[str] = []
		prefix = f"Episode {episode_num}"

		if not entry.get("title"):
			errors.append(f"{prefix}: Missing required field: title")

		# enclosure (audio file)
		enclosures = entry.get("enclosures") or []
		if not enclosures:
			errors.append(f"{prefix}: Missing required enclosure (audio file)")
		else:
			enc = enclosures[0]
			if not enc.get("url"):
				errors.append(f"{prefix}: Enclosure missing URL")

		if not entry.get("published") and not entry.get("updated"):
			errors.append(f"{prefix}: Missing required field: pubDate")

		if not entry.get("id"):
			errors.append(f"{prefix}: Missing required field: guid")

		return errors

	def _validate_spotify(self, feed: Any) -> Dict[str, Any]:
		"""
		Validate RSS feed against Spotify Podcasters requirements.

		Checks XML structure, audio format support, and episode duration limits.

		Args:
			feed: Parsed feedparser feed object

		Returns:
			{"valid": bool, "errors": [str]}
		"""
		errors: List[str] = []

		if feed.bozo and feed.bozo_exception:
			errors.append(f"RSS parse error: {feed.bozo_exception}")

		# Feed must have at least a title
		if not feed.feed.get("title"):
			errors.append("Missing channel title")

		# Episode validation
		for i, entry in enumerate(feed.entries):
			ep_errors = self._validate_spotify_episode(entry, i + 1)
			errors.extend(ep_errors)

		return {"valid": len(errors) == 0, "errors": errors}

	def _validate_spotify_episode(self, entry: Any, episode_num: int) -> List[str]:
		"""
		Validate a single episode for Spotify compliance.

		Args:
			entry: feedparser entry object
			episode_num: Episode position (for error messages)

		Returns:
			List of error strings
		"""
		errors: List[str] = []
		prefix = f"Episode {episode_num}"

		enclosures = entry.get("enclosures") or []
		if not enclosures:
			errors.append(f"{prefix}: Missing enclosure (audio file)")
		else:
			enc = enclosures[0]
			enc_type = (enc.get("type") or "").lower()
			if enc_type and enc_type not in SUPPORTED_AUDIO_TYPES:
				errors.append(
					f"{prefix}: Unsupported audio format '{enc_type}'. "
					f"Supported: {', '.join(sorted(SUPPORTED_AUDIO_TYPES))}"
				)

		# Duration check (15 seconds to 12 hours)
		duration_raw = entry.get("itunes_duration")
		if duration_raw is not None:
			duration_seconds = _parse_duration(duration_raw)
			if duration_seconds is not None:
				if duration_seconds < 15:
					errors.append(
						f"{prefix}: Duration {duration_seconds}s is below minimum (15 seconds)"
					)
				elif duration_seconds > 43200:  # 12 hours
					errors.append(
						f"{prefix}: Duration {duration_seconds}s exceeds maximum (12 hours / 43200 seconds)"
					)

		return errors

	def _validate_google_podcasts(self, feed: Any) -> Dict[str, Any]:
		"""
		Validate RSS feed against Google Podcasts requirements.

		Checks RSS 2.0 structure and valid enclosure URLs.

		Args:
			feed: Parsed feedparser feed object

		Returns:
			{"valid": bool, "errors": [str]}
		"""
		errors: List[str] = []

		if feed.bozo and feed.bozo_exception:
			errors.append(f"RSS parse error: {feed.bozo_exception}")

		channel = feed.feed

		# Required fields for Google Podcasts
		if not channel.get("title"):
			errors.append("Missing required channel field: title")
		if not channel.get("description") and not channel.get("summary"):
			errors.append("Missing required channel field: description")

		# Check episodes have valid enclosures
		for i, entry in enumerate(feed.entries):
			enclosures = entry.get("enclosures") or []
			if not enclosures:
				errors.append(f"Episode {i + 1}: Missing enclosure (audio file)")
			else:
				enc = enclosures[0]
				if not enc.get("url") or not str(enc.get("url", "")).startswith("http"):
					errors.append(f"Episode {i + 1}: Enclosure URL must be a valid HTTP/HTTPS URL")

		return {"valid": len(errors) == 0, "errors": errors}


def _parse_duration(duration_raw: Any) -> Optional[int]:
	"""
	Parse iTunes duration value to seconds.

	Handles formats: seconds (int/str), HH:MM:SS, MM:SS.

	Args:
		duration_raw: Raw duration value from feedparser

	Returns:
		Duration in seconds, or None if unparseable
	"""
	try:
		# Plain integer seconds
		return int(duration_raw)
	except (ValueError, TypeError):
		pass

	try:
		# HH:MM:SS or MM:SS format
		parts = str(duration_raw).split(":")
		if len(parts) == 3:
			return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
		elif len(parts) == 2:
			return int(parts[0]) * 60 + int(parts[1])
	except (ValueError, TypeError):
		pass

	return None
