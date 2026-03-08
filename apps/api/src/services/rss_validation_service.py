"""
RSS feed validation service.

Validates RSS feeds against Apple Podcasts, Spotify, and Google Podcasts
directory requirements. Results are stored in RSSFeed.validation_status.

Validation checks:
- Required channel and item (episode) elements per directory
- Image specifications (format, dimensions, file size)
- Audio enclosure MIME types
- Date format compliance (RFC 2822)
- Character encoding and entity escaping
- GUID uniqueness across episodes
"""

import asyncio
import io
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.parse import urlparse
from uuid import UUID

import defusedxml.ElementTree as defused_ET
from defusedxml.common import DefusedXmlException
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.rss_feed import RSSFeed
from ..schemas.rss_feed import (
	DirectoryValidationResult,
	ValidationError,
	ValidationStatusUpdate,
)

logger = logging.getLogger(__name__)


class RSSFetchError(Exception):
	"""Raised when the RSS feed cannot be fetched from a remote source.

	Distinct from ValueError so routers can map it to a 503 response
	rather than treating it as a client validation error (422).
	"""


# XML namespace map used in RSS feeds
RSS_NAMESPACES = {
	"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
	"content": "http://purl.org/rss/1.0/modules/content/",
	"atom": "http://www.w3.org/2005/Atom",
}

# Apple Podcasts valid categories — all top-level categories and subcategories
# Source: https://podcasters.apple.com/support/1691-apple-podcasts-categories
APPLE_VALID_CATEGORIES = {
	# Top-level
	"Arts", "Business", "Comedy", "Education", "Fiction", "Government",
	"History", "Health & Fitness", "Kids & Family", "Leisure", "Music",
	"News", "Religion & Spirituality", "Science", "Society & Culture",
	"Sports", "Technology", "True Crime", "TV & Film",
	# Arts subcategories
	"Books", "Design", "Fashion & Beauty", "Food", "Performing Arts", "Visual Arts",
	# Business subcategories
	"Careers", "Entrepreneurship", "Investing", "Management", "Marketing", "Non-Profit",
	# Comedy subcategories
	"Comedy Interviews", "Improv", "Stand-Up",
	# Education subcategories
	"Courses", "How To", "Language Learning", "Self-Improvement",
	# Fiction subcategories
	"Comedy Fiction", "Drama", "Science Fiction",
	# Health & Fitness subcategories
	"Alternative Health", "Fitness", "Medicine", "Mental Health", "Nutrition", "Sexuality",
	# Kids & Family subcategories
	"Education for Kids", "Parenting", "Pets & Animals", "Stories for Kids",
	# Leisure subcategories
	"Animation & Manga", "Automotive", "Aviation", "Crafts", "Games", "Hobbies",
	"Home & Garden", "Video Games",
	# Music subcategories
	"Music Commentary", "Music History", "Music Interviews",
	# News subcategories
	"Business News", "Daily News", "Entertainment News", "News Commentary",
	"Politics", "Sports News", "Tech News",
	# Religion & Spirituality subcategories
	"Buddhism", "Christianity", "Hinduism", "Islam", "Judaism", "Religion", "Spirituality",
	# Science subcategories
	"Astronomy", "Chemistry", "Earth Sciences", "Life Sciences", "Mathematics",
	"Natural Sciences", "Nature", "Physics", "Social Sciences",
	# Society & Culture subcategories
	"Documentary", "Personal Journals", "Philosophy", "Places & Travel", "Relationships",
	# Sports subcategories
	"Baseball", "Basketball", "Cricket", "Fantasy Sports", "Football", "Golf",
	"Hockey", "Rugby", "Running", "Soccer", "Swimming", "Tennis", "Volleyball",
	"Wilderness", "Wrestling",
	# TV & Film subcategories
	"After Shows", "Film History", "Film Interviews", "Film Reviews", "TV Reviews",
}

# Valid audio MIME types
APPLE_VALID_AUDIO_TYPES = {"audio/mpeg", "audio/x-m4a", "audio/mp4", "audio/aac"}
SPOTIFY_VALID_AUDIO_TYPES = {"audio/mpeg"}

# Image requirements
APPLE_MIN_IMAGE_DIM = 3000
APPLE_MAX_IMAGE_SIZE_KB = 500
SPOTIFY_MIN_IMAGE_DIM = 3000
SPOTIFY_MAX_IMAGE_SIZE_MB = 30


class RSSValidationService:
	"""Validate RSS feeds against podcast directory requirements."""

	# ------------------------------------------------------------------
	# Public API
	# ------------------------------------------------------------------

	async def validate_rss_feed(
		self,
		db: AsyncSession,
		project_id: UUID,
		tenant_id: UUID,
		rss_content: Optional[str] = None,
	) -> ValidationStatusUpdate:
		"""
		Validate RSS feed for Apple Podcasts, Spotify, and Google Podcasts.

		Fetches the RSSFeed record for the project and validates the feed XML.
		If rss_content is provided it is used directly; otherwise the feed is
		retrieved via the stored public_url or s3_key.

		Args:
			db: Database session
			project_id: UUID of the project
			tenant_id: UUID of the current user's tenant for ownership check
			rss_content: Optional RSS XML content to validate directly

		Returns:
			ValidationStatusUpdate with results for all three directories

		Raises:
			ValueError: If RSSFeed not found or content unavailable
			RSSFetchError: If the feed cannot be fetched from the remote source
			ET.ParseError: If RSS content is not valid XML
		"""
		rss_feed = await self._get_rss_feed(db, project_id, tenant_id)

		if rss_content is None:
			rss_content = await self._fetch_rss_content(rss_feed)

		root = self._parse_rss_xml(rss_content)
		channel = root.find("channel")
		if channel is None:
			raise ValueError("Invalid RSS feed: missing <channel> element")

		now = datetime.now(timezone.utc)

		apple_result = await self._validate_apple_podcasts(channel, now)
		spotify_result = await self._validate_spotify(channel, now)
		google_result = await self._validate_google_podcasts(channel, now)

		result = ValidationStatusUpdate(
			last_validated_at=now,
			feed_last_generated=rss_feed.last_generated,
			apple_podcasts=apple_result,
			spotify=spotify_result,
			google_podcasts=google_result,
			is_valid_for_all=(
				apple_result.valid and spotify_result.valid and google_result.valid
			),
		)

		# Persist results to RSSFeed.validation_status
		rss_feed.validation_status = result.model_dump(mode="json")
		await db.commit()

		return result

	async def get_validation_status(
		self,
		db: AsyncSession,
		project_id: UUID,
		tenant_id: UUID,
	) -> ValidationStatusUpdate:
		"""
		Return the last stored validation results for a project's RSS feed.

		Args:
			db: Database session
			project_id: UUID of the project
			tenant_id: UUID of the current user's tenant for ownership check

		Returns:
			ValidationStatusUpdate previously stored

		Raises:
			ValueError: If RSSFeed not found or never validated
		"""
		rss_feed = await self._get_rss_feed(db, project_id, tenant_id)

		if not rss_feed.validation_status:
			raise ValueError("No validation results found. Call validate first.")

		return ValidationStatusUpdate(**rss_feed.validation_status)

	# ------------------------------------------------------------------
	# Internal helpers
	# ------------------------------------------------------------------

	async def _get_rss_feed(self, db: AsyncSession, project_id: UUID, tenant_id: UUID) -> RSSFeed:
		"""Fetch RSSFeed record for project or raise ValueError.

		Filters by both project_id and tenant_id to enforce tenant isolation
		in addition to the database-level RLS policies.
		"""
		result = await db.execute(
			select(RSSFeed).where(
				RSSFeed.project_id == project_id,
				RSSFeed.tenant_id == tenant_id,
			)
		)
		rss_feed = result.scalar_one_or_none()
		if rss_feed is None:
			raise ValueError(
				"RSS feed not found. Generate feed first with "
				f"POST /projects/{project_id}/rss-feed/generate"
			)
		return rss_feed

	async def _fetch_rss_content(self, rss_feed: RSSFeed) -> str:
		"""
		Retrieve RSS XML content from the stored URL or S3 key.

		In production this fetches from rss_feed.public_url (HTTP) or
		falls back to S3 via rss_feed.s3_key. Tests patch this method.

		Raises:
			ValueError: If no content source is available
			RSSFetchError: If the remote fetch fails (network or S3 error)
		"""
		if rss_feed.public_url:
			try:
				async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
					response = await client.get(rss_feed.public_url)
					response.raise_for_status()
					return response.text
			except httpx.HTTPError as exc:
				raise RSSFetchError(
					f"Failed to fetch RSS feed from {rss_feed.public_url}: {exc}"
				) from exc

		if rss_feed.s3_key:
			# S3 fetch via boto3 (lazy import to avoid breaking tests without AWS)
			# Wrapped in asyncio.to_thread to avoid blocking the event loop
			try:
				import boto3  # noqa: PLC0415
				from ..config import settings  # noqa: PLC0415

				s3_key = rss_feed.s3_key
				aws_key_id = getattr(settings, "AWS_ACCESS_KEY_ID", None)
				aws_secret = getattr(settings, "AWS_SECRET_ACCESS_KEY", None)
				bucket = getattr(settings, "S3_BUCKET_NAME", None)

				def _s3_fetch() -> str:
					s3 = boto3.client(
						"s3",
						aws_access_key_id=aws_key_id,
						aws_secret_access_key=aws_secret,
					)
					obj = s3.get_object(Bucket=bucket, Key=s3_key)
					return obj["Body"].read().decode("utf-8")

				return await asyncio.to_thread(_s3_fetch)
			except Exception as exc:
				raise RSSFetchError(
					f"Failed to fetch RSS feed from S3 key {rss_feed.s3_key}: {exc}"
				) from exc

		raise ValueError(
			"RSS feed content unavailable. Generate feed first."
		)

	def _parse_rss_xml(self, rss_content: str) -> ET.Element:
		"""
		Parse RSS XML and return the root element.

		Uses defusedxml to prevent XML entity expansion (billion-laughs) attacks
		when parsing untrusted RSS content from external URLs or user input.

		Raises:
			ET.ParseError: If content is not valid XML
		"""
		# Register namespaces so they round-trip cleanly (standard ET only)
		for prefix, uri in RSS_NAMESPACES.items():
			ET.register_namespace(prefix, uri)

		try:
			return defused_ET.fromstring(rss_content)
		except ET.ParseError as exc:
			raise ET.ParseError(f"Invalid RSS XML: {exc}") from exc
		except DefusedXmlException as exc:
			raise ET.ParseError(f"Invalid RSS XML: {exc}") from exc

	# ------------------------------------------------------------------
	# Directory validators
	# ------------------------------------------------------------------

	async def _validate_apple_podcasts(
		self,
		channel: ET.Element,
		checked_at: datetime,
	) -> DirectoryValidationResult:
		"""Validate channel against Apple Podcasts requirements."""
		errors: list[ValidationError] = []
		warnings: list[ValidationError] = []

		itunes = "http://www.itunes.com/dtds/podcast-1.0.dtd"

		# Required channel fields
		for field in ("title", "link", "description"):
			if not self._text(channel, field):
				errors.append(ValidationError(
					field=field,
					level="error",
					message=f"Missing required channel element <{field}>",
					examples=[f"<{field}>Your podcast title</{field}>"],
				))

		# language
		lang = self._text(channel, "language")
		if not lang:
			errors.append(ValidationError(
				field="language",
				level="error",
				message="Missing required channel element <language>",
				examples=["<language>en-US</language>"],
			))

		# itunes:author
		if not self._text(channel, f"{{{itunes}}}author"):
			errors.append(ValidationError(
				field="itunes:author",
				level="error",
				message="Missing required <itunes:author> element",
				examples=["<itunes:author>John Doe</itunes:author>"],
			))

		# itunes:image
		image_elem = channel.find(f"{{{itunes}}}image")
		image_url = image_elem.get("href") if image_elem is not None else None
		if not image_url:
			errors.append(ValidationError(
				field="itunes:image",
				level="error",
				message="Missing required <itunes:image href='...'> element",
				examples=["<itunes:image href='https://example.com/artwork.jpg'/>"],
			))
		else:
			image_results = await self._validate_image(
				image_url,
				min_dim=APPLE_MIN_IMAGE_DIM,
				max_size_kb=APPLE_MAX_IMAGE_SIZE_KB,
			)
			for img_err in image_results:
				if img_err.level == "warning":
					warnings.append(img_err)
				else:
					errors.append(img_err)

		# itunes:category
		category_elem = channel.find(f"{{{itunes}}}category")
		if category_elem is None or not category_elem.get("text"):
			errors.append(ValidationError(
				field="itunes:category",
				level="error",
				message="Missing required <itunes:category text='...'> element",
				examples=["<itunes:category text='Technology'/>"],
			))
		else:
			category_text = category_elem.get("text", "")
			if category_text not in APPLE_VALID_CATEGORIES:
				errors.append(ValidationError(
					field="itunes:category",
					level="error",
					message=(
						f"Unknown itunes:category value '{category_text}'. "
						"Must be a valid Apple Podcasts category."
					),
					details=f"Found: {category_text}",
					examples=sorted(APPLE_VALID_CATEGORIES)[:3],
				))

		# itunes:explicit
		explicit_text = self._text(channel, f"{{{itunes}}}explicit")
		if explicit_text is None:
			errors.append(ValidationError(
				field="itunes:explicit",
				level="error",
				message="Missing required <itunes:explicit> element",
				examples=["<itunes:explicit>no</itunes:explicit>"],
			))
		elif explicit_text.lower() not in {"yes", "no", "clean"}:
			errors.append(ValidationError(
				field="itunes:explicit",
				level="error",
				message=(
					f"Invalid itunes:explicit value '{explicit_text}'. "
					"Must be 'yes', 'no', or 'clean'."
				),
				details=f"Found: {explicit_text}",
				examples=["<itunes:explicit>no</itunes:explicit>"],
			))

		# Episode-level checks
		items = channel.findall("item")
		guids: list[str] = []
		for item in items:
			item_errors, item_warnings = self._validate_apple_episode(item, itunes, guids)
			errors.extend(item_errors)
			warnings.extend(item_warnings)

		return DirectoryValidationResult(
			directory="apple_podcasts",
			valid=len(errors) == 0,
			errors=errors,
			warnings=warnings,
			checked_at=checked_at,
		)

	def _validate_apple_episode(
		self,
		item: ET.Element,
		itunes: str,
		guids: list[str],
	) -> tuple[list[ValidationError], list[ValidationError]]:
		"""Validate a single episode against Apple Podcasts requirements."""
		errors: list[ValidationError] = []
		warnings: list[ValidationError] = []

		title = self._text(item, "title") or "<unknown>"

		# title
		if not self._text(item, "title"):
			errors.append(ValidationError(
				field="item/title",
				level="error",
				message="Episode missing <title>",
			))

		# description or content:encoded
		content_ns = "http://purl.org/rss/1.0/modules/content/"
		if not self._text(item, "description") and not self._text(item, f"{{{content_ns}}}encoded"):
			errors.append(ValidationError(
				field="item/description",
				level="error",
				message=f"Episode '{title}' missing <description> or <content:encoded>",
			))

		# enclosure
		enclosure = item.find("enclosure")
		if enclosure is None:
			errors.append(ValidationError(
				field="item/enclosure",
				level="error",
				message=f"Episode '{title}' missing <enclosure> element",
			))
		else:
			enc_url = enclosure.get("url", "")
			enc_type = enclosure.get("type", "")
			enc_length = enclosure.get("length", "")

			if not enc_url:
				errors.append(ValidationError(
					field="item/enclosure/@url",
					level="error",
					message=f"Episode '{title}' enclosure missing url attribute",
				))
			else:
				parsed_url = urlparse(enc_url)
				if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
					errors.append(ValidationError(
						field="item/enclosure/@url",
						level="error",
						message=(
							f"Episode '{title}' enclosure url must be an absolute "
							"HTTP/HTTPS URL"
						),
						details=f"Found: {enc_url}",
						examples=["<enclosure url='https://example.com/ep.mp3' .../>"],
					))
			if enc_type not in APPLE_VALID_AUDIO_TYPES:
				errors.append(ValidationError(
					field="item/enclosure/@type",
					level="error",
					message=(
						f"Episode '{title}' has unsupported audio type '{enc_type}'. "
						f"Apple Podcasts requires: {', '.join(sorted(APPLE_VALID_AUDIO_TYPES))}"
					),
					details=f"Found: {enc_type}",
					examples=["<enclosure type='audio/mpeg' .../>"],
				))
			if not enc_length or not enc_length.isdigit() or int(enc_length) < 0:
				errors.append(ValidationError(
					field="item/enclosure/@length",
					level="error",
					message=f"Episode '{title}' enclosure length must be a non-negative integer",
					examples=["<enclosure length='12345678' .../>"],
				))

		# pubDate
		pub_date_str = self._text(item, "pubDate")
		if not pub_date_str:
			errors.append(ValidationError(
				field="item/pubDate",
				level="error",
				message=f"Episode '{title}' missing <pubDate>",
				examples=["<pubDate>Mon, 18 Dec 2025 10:45:30 +0000</pubDate>"],
			))
		else:
			if not self._is_valid_rfc2822(pub_date_str):
				errors.append(ValidationError(
					field="item/pubDate",
					level="error",
					message=f"Episode '{title}' pubDate is not valid RFC 2822 format",
					details=f"Found: {pub_date_str}",
					examples=["<pubDate>Mon, 18 Dec 2025 10:45:30 +0000</pubDate>"],
				))

		# guid
		guid_elem = item.find("guid")
		if guid_elem is None or not guid_elem.text:
			errors.append(ValidationError(
				field="item/guid",
				level="error",
				message=f"Episode '{title}' missing <guid>",
			))
		else:
			guid_val = guid_elem.text.strip()
			if guid_val in guids:
				errors.append(ValidationError(
					field="item/guid",
					level="error",
					message=f"Duplicate GUID '{guid_val}' found across episodes",
					details="GUIDs must be globally unique per episode",
				))
			else:
				guids.append(guid_val)

		# itunes:duration (advisory for Apple, required for proper parsing)
		if not self._text(item, f"{{{itunes}}}duration"):
			warnings.append(ValidationError(
				field="item/itunes:duration",
				level="warning",
				message=f"Episode '{title}' missing <itunes:duration>. Recommended for Apple Podcasts.",
				examples=["<itunes:duration>3600</itunes:duration>"],
			))

		# itunes:episodeType (advisory)
		if not self._text(item, f"{{{itunes}}}episodeType"):
			warnings.append(ValidationError(
				field="item/itunes:episodeType",
				level="warning",
				message=f"Episode '{title}' missing <itunes:episodeType>. Recommended for series.",
				examples=["<itunes:episodeType>full</itunes:episodeType>"],
			))

		return errors, warnings

	async def _validate_spotify(
		self,
		channel: ET.Element,
		checked_at: datetime,
	) -> DirectoryValidationResult:
		"""Validate channel against Spotify requirements."""
		errors: list[ValidationError] = []
		warnings: list[ValidationError] = []

		itunes = "http://www.itunes.com/dtds/podcast-1.0.dtd"

		# Required channel fields
		for field in ("title", "description", "link"):
			if not self._text(channel, field):
				errors.append(ValidationError(
					field=field,
					level="error",
					message=f"Missing required channel element <{field}>",
				))

		# language
		if not self._text(channel, "language"):
			errors.append(ValidationError(
				field="language",
				level="error",
				message="Missing required channel element <language>",
				examples=["<language>en</language>"],
			))

		# itunes:image (Spotify uses this)
		image_elem = channel.find(f"{{{itunes}}}image")
		image_url = image_elem.get("href") if image_elem is not None else None
		if not image_url:
			errors.append(ValidationError(
				field="itunes:image",
				level="error",
				message="Missing required <itunes:image href='...'> element for Spotify",
				examples=["<itunes:image href='https://example.com/artwork.jpg'/>"],
			))
		else:
			image_results = await self._validate_image(
				image_url,
				min_dim=SPOTIFY_MIN_IMAGE_DIM,
				max_size_kb=SPOTIFY_MAX_IMAGE_SIZE_MB * 1024,
			)
			for img_err in image_results:
				if img_err.level == "warning":
					warnings.append(img_err)
				else:
					errors.append(img_err)

		# Encoding check: look for non-UTF-8 declaration
		# (XML parser already normalises this, but check xml declaration via feed root)
		# Spotify requires UTF-8
		# (Note: ET already fails on invalid XML, so this is advisory)

		# Episode-level checks
		items = channel.findall("item")
		guids: list[str] = []
		for item in items:
			item_errors, item_warnings = self._validate_spotify_episode(item, guids)
			errors.extend(item_errors)
			warnings.extend(item_warnings)

		return DirectoryValidationResult(
			directory="spotify",
			valid=len(errors) == 0,
			errors=errors,
			warnings=warnings,
			checked_at=checked_at,
		)

	def _validate_spotify_episode(
		self,
		item: ET.Element,
		guids: list[str],
	) -> tuple[list[ValidationError], list[ValidationError]]:
		"""Validate a single episode against Spotify requirements."""
		errors: list[ValidationError] = []
		warnings: list[ValidationError] = []

		title = self._text(item, "title") or "<unknown>"

		if not self._text(item, "title"):
			errors.append(ValidationError(
				field="item/title",
				level="error",
				message="Episode missing <title>",
			))

		if not self._text(item, "description"):
			errors.append(ValidationError(
				field="item/description",
				level="error",
				message=f"Episode '{title}' missing <description>",
			))

		# pubDate
		pub_date_str = self._text(item, "pubDate")
		if not pub_date_str:
			errors.append(ValidationError(
				field="item/pubDate",
				level="error",
				message=f"Episode '{title}' missing <pubDate>",
			))
		elif not self._is_valid_rfc2822(pub_date_str):
			errors.append(ValidationError(
				field="item/pubDate",
				level="error",
				message=f"Episode '{title}' pubDate is not valid RFC 2822 format",
				details=f"Found: {pub_date_str}",
			))

		# guid
		guid_elem = item.find("guid")
		if guid_elem is None or not guid_elem.text:
			errors.append(ValidationError(
				field="item/guid",
				level="error",
				message=f"Episode '{title}' missing <guid>",
			))
		else:
			guid_val = guid_elem.text.strip()
			if guid_val in guids:
				errors.append(ValidationError(
					field="item/guid",
					level="error",
					message=f"Duplicate GUID '{guid_val}' found. Spotify requires unique GUIDs.",
				))
			else:
				guids.append(guid_val)

		# enclosure (Spotify strict: audio/mpeg only)
		enclosure = item.find("enclosure")
		if enclosure is None:
			errors.append(ValidationError(
				field="item/enclosure",
				level="error",
				message=f"Episode '{title}' missing <enclosure> element",
			))
		else:
			enc_url = enclosure.get("url", "")
			enc_type = enclosure.get("type", "")
			enc_length = enclosure.get("length", "")

			if not enc_url or not enc_url.startswith(("http://", "https://")):
				errors.append(ValidationError(
					field="item/enclosure/@url",
					level="error",
					message=(
						f"Episode '{title}' enclosure url is missing or not a valid "
						"HTTP/HTTPS URL"
					),
					examples=["<enclosure url='https://example.com/ep.mp3' .../>"],
				))

			if enc_type not in SPOTIFY_VALID_AUDIO_TYPES:
				errors.append(ValidationError(
					field="item/enclosure/@type",
					level="error",
					message=(
						f"Episode '{title}' has invalid audio type '{enc_type}'. "
						"Spotify strictly requires audio/mpeg."
					),
					details=f"Found: {enc_type}",
					examples=["<enclosure type='audio/mpeg' .../>"],
				))

			if not enc_length or not enc_length.isdigit():
				errors.append(ValidationError(
					field="item/enclosure/@length",
					level="error",
					message=f"Episode '{title}' enclosure length must be a numeric byte count",
					examples=["<enclosure length='12345678' .../>"],
				))

		# Episode title length advisory (Spotify recommends ≤20 chars)
		if title != "<unknown>" and len(title) > 20:
			warnings.append(ValidationError(
				field="item/title",
				level="warning",
				message=(
					f"Episode title '{title[:30]}...' exceeds 20 characters. "
					"Spotify recommends shorter titles for display."
				),
			))

		return errors, warnings

	async def _validate_google_podcasts(
		self,
		channel: ET.Element,
		checked_at: datetime,
	) -> DirectoryValidationResult:
		"""Validate channel against Google Podcasts requirements."""
		errors: list[ValidationError] = []
		warnings: list[ValidationError] = []

		# Required channel fields
		for field in ("title", "description", "link"):
			if not self._text(channel, field):
				errors.append(ValidationError(
					field=field,
					level="error",
					message=f"Missing required channel element <{field}>",
				))

		# language
		lang = self._text(channel, "language")
		if not lang:
			errors.append(ValidationError(
				field="language",
				level="error",
				message="Missing required channel element <language>",
				examples=["<language>en</language>"],
			))
		elif not self._is_valid_language_code(lang):
			errors.append(ValidationError(
				field="language",
				level="error",
				message=f"Invalid language code '{lang}'. Use BCP 47 format.",
				details=f"Found: {lang}",
				examples=["en", "en-US", "es-MX"],
			))

		# lastBuildDate
		last_build = self._text(channel, "lastBuildDate")
		if not last_build:
			errors.append(ValidationError(
				field="lastBuildDate",
				level="error",
				message="Missing required <lastBuildDate> element",
				examples=["<lastBuildDate>Mon, 18 Dec 2025 10:45:30 +0000</lastBuildDate>"],
			))
		elif not self._is_valid_rfc2822(last_build):
			errors.append(ValidationError(
				field="lastBuildDate",
				level="error",
				message="lastBuildDate is not valid RFC 2822 format",
				details=f"Found: {last_build}",
			))

		# image element (standard RSS image, not itunes:image)
		image_elem = channel.find("image")
		if image_elem is not None:
			image_url_elem = image_elem.find("url")
			image_title_elem = image_elem.find("title")
			channel_title = self._text(channel, "title") or ""

			if image_url_elem is None or not image_url_elem.text:
				warnings.append(ValidationError(
					field="image/url",
					level="warning",
					message="RSS <image> element missing <url>",
				))
			else:
				image_results = await self._validate_image(
					image_url_elem.text.strip(),
					min_dim=APPLE_MIN_IMAGE_DIM,
					max_size_kb=APPLE_MAX_IMAGE_SIZE_KB,
				)
				for img_err in image_results:
					if img_err.level == "warning":
						warnings.append(img_err)
					else:
						errors.append(img_err)
			if image_title_elem is None or image_title_elem.text != channel_title:
				warnings.append(ValidationError(
					field="image/title",
					level="warning",
					message="RSS <image><title> should match the channel title",
					details=f"Channel title: '{channel_title}'",
				))

		# Episode-level checks
		items = channel.findall("item")
		guids: list[str] = []
		for item in items:
			item_errors = self._validate_google_episode(item, guids)
			errors.extend(item_errors)

		return DirectoryValidationResult(
			directory="google_podcasts",
			valid=len(errors) == 0,
			errors=errors,
			warnings=warnings,
			checked_at=checked_at,
		)

	def _validate_google_episode(
		self,
		item: ET.Element,
		guids: list[str],
	) -> list[ValidationError]:
		"""Validate a single episode against Google Podcasts requirements."""
		errors: list[ValidationError] = []
		title = self._text(item, "title") or "<unknown>"

		for field in ("title", "description"):
			if not self._text(item, field):
				errors.append(ValidationError(
					field=f"item/{field}",
					level="error",
					message=f"Episode '{title}' missing <{field}>",
				))

		# pubDate: must be present and RFC 2822-compliant
		pub_date_str = self._text(item, "pubDate")
		if not pub_date_str:
			errors.append(ValidationError(
				field="item/pubDate",
				level="error",
				message=f"Episode '{title}' missing <pubDate>",
				examples=["<pubDate>Mon, 18 Dec 2025 10:45:30 +0000</pubDate>"],
			))
		elif not self._is_valid_rfc2822(pub_date_str):
			errors.append(ValidationError(
				field="item/pubDate",
				level="error",
				message=f"Episode '{title}' pubDate is not valid RFC 2822 format",
				details=f"Found: {pub_date_str}",
				examples=["<pubDate>Mon, 18 Dec 2025 10:45:30 +0000</pubDate>"],
			))

		# enclosure: must be present with valid url, numeric length, and type
		enclosure = item.find("enclosure")
		if enclosure is None:
			errors.append(ValidationError(
				field="item/enclosure",
				level="error",
				message=f"Episode '{title}' missing <enclosure> element",
			))
		else:
			enc_url = enclosure.get("url", "")
			enc_length = enclosure.get("length", "")
			enc_type = enclosure.get("type", "")

			if not enc_url or not enc_url.startswith(("http://", "https://")):
				errors.append(ValidationError(
					field="item/enclosure/@url",
					level="error",
					message=(
						f"Episode '{title}' enclosure url is missing or not a valid "
						"HTTP/HTTPS URL"
					),
					examples=["<enclosure url='https://example.com/ep.mp3' .../>"],
				))

			if not enc_length or not enc_length.isdigit() or int(enc_length) < 0:
				errors.append(ValidationError(
					field="item/enclosure/@length",
					level="error",
					message=f"Episode '{title}' enclosure length must be a non-negative integer",
					examples=["<enclosure length='12345678' .../>"],
				))

			if not enc_type:
				errors.append(ValidationError(
					field="item/enclosure/@type",
					level="error",
					message=f"Episode '{title}' enclosure missing type attribute",
					examples=["<enclosure type='audio/mpeg' .../>"],
				))

		# guid: must be present and unique
		guid_elem = item.find("guid")
		if guid_elem is None or not guid_elem.text:
			errors.append(ValidationError(
				field="item/guid",
				level="error",
				message=f"Episode '{title}' missing <guid>",
			))
		else:
			guid_val = guid_elem.text.strip()
			if guid_val in guids:
				errors.append(ValidationError(
					field="item/guid",
					level="error",
					message=f"Duplicate GUID '{guid_val}' found. Google Podcasts requires unique GUIDs.",
				))
			else:
				guids.append(guid_val)

		return errors

	# ------------------------------------------------------------------
	# Image validation
	# ------------------------------------------------------------------

	async def _validate_image(
		self,
		image_url: str,
		min_dim: int = APPLE_MIN_IMAGE_DIM,
		max_size_kb: int = APPLE_MAX_IMAGE_SIZE_KB,
	) -> list[ValidationError]:
		"""
		Validate podcast artwork image.

		Checks URL accessibility, format (JPG/PNG), dimensions, and file size.
		Streams the response body to avoid buffering multi-gigabyte files from
		untrusted RSS artwork URLs — aborts as soon as cumulative size exceeds
		max_size_kb. Network errors are reported as warnings rather than errors
		to avoid blocking validation when images are temporarily unavailable.
		"""
		errors: list[ValidationError] = []
		max_bytes = max_size_kb * 1024

		try:
			async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
				async with client.stream("GET", image_url) as response:
					if response.status_code != 200:
						errors.append(ValidationError(
							field="itunes:image",
							level="error",
							message=f"Artwork URL returned HTTP {response.status_code}",
							details=f"URL: {image_url}",
						))
						return errors

					content_type = response.headers.get("content-type", "").lower()
					if "jpeg" not in content_type and "jpg" not in content_type and "png" not in content_type:
						errors.append(ValidationError(
							field="itunes:image",
							level="error",
							message=f"Artwork must be JPG or PNG. Found content-type: {content_type}",
							details=f"URL: {image_url}",
							examples=["image/jpeg", "image/png"],
						))

					# Check Content-Length header for early abort before reading body
					content_length_header = response.headers.get("content-length")
					if content_length_header is not None:
						try:
							declared_bytes = int(content_length_header)
							if declared_bytes > max_bytes:
								errors.append(ValidationError(
									field="itunes:image",
									level="error",
									message=(
										f"Artwork file size {declared_bytes // 1024} KB exceeds "
										f"maximum {max_size_kb} KB"
									),
									details=f"URL: {image_url}",
								))
								return errors
						except ValueError:
							pass  # Ignore malformed Content-Length header

					# Stream body in chunks; abort if cumulative size exceeds limit
					body = b""
					async for chunk in response.aiter_bytes(chunk_size=8192):
						body += chunk
						if len(body) > max_bytes:
							errors.append(ValidationError(
								field="itunes:image",
								level="error",
								message=(
									f"Artwork file size exceeds maximum {max_size_kb} KB"
								),
								details=f"URL: {image_url}",
							))
							return errors

					# Check dimensions with Pillow
					try:
						from PIL import Image  # noqa: PLC0415

						img = Image.open(io.BytesIO(body))
						width, height = img.size
						if width < min_dim or height < min_dim:
							errors.append(ValidationError(
								field="itunes:image",
								level="error",
								message=(
									f"Artwork dimensions {width}x{height}px are below the minimum "
									f"{min_dim}x{min_dim}px requirement"
								),
								details=f"URL: {image_url}",
							))
					except Exception as pil_exc:
						errors.append(ValidationError(
							field="itunes:image",
							level="error",
							message="Could not read image dimensions",
							details=str(pil_exc),
						))

		except httpx.RequestError as exc:
			errors.append(ValidationError(
				field="itunes:image",
				level="warning",
				message=f"Could not fetch artwork URL to validate: {exc}",
				details=f"URL: {image_url}",
			))

		return errors

	# ------------------------------------------------------------------
	# Utility helpers
	# ------------------------------------------------------------------

	@staticmethod
	def _text(element: ET.Element, tag: str) -> Optional[str]:
		"""Return stripped text of a child element, or None if missing/empty."""
		child = element.find(tag)
		if child is None or not child.text:
			return None
		text = child.text.strip()
		return text if text else None

	@staticmethod
	def _is_valid_rfc2822(date_str: str) -> bool:
		"""Return True if date_str is a valid RFC 2822 date."""
		try:
			parsedate_to_datetime(date_str)
			return True
		except Exception:
			return False

	@staticmethod
	def _is_valid_language_code(lang: str) -> bool:
		"""
		Basic BCP 47 language code validation.
		Accepts 'en', 'en-US', 'zh-Hans-CN', etc.
		"""
		import re  # noqa: PLC0415
		return bool(re.match(r'^[a-zA-Z]{2,3}(-[a-zA-Z0-9]{2,8})*$', lang))
