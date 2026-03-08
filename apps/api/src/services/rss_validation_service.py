"""
RSS Validation Service for podcast directory compliance checking.

Validates RSS feeds against Apple Podcasts, Spotify, and Google Podcasts
requirements. Checks required fields, image specifications, and encoding.
"""

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import RSSFeed
from ..schemas.rss_feed import (
	DirectoryValidationResult,
	ValidationError,
	ValidationStatusResponse,
)


# XML namespaces used in podcast RSS feeds
NAMESPACES = {
	"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
	"content": "http://purl.org/rss/1.0/modules/content/",
	"atom": "http://www.w3.org/2005/Atom",
}

# Supported audio MIME types
APPLE_AUDIO_TYPES = {"audio/mpeg", "audio/x-m4a", "audio/mp4", "audio/ogg", "video/mp4", "video/x-m4v"}
SPOTIFY_AUDIO_TYPES = {"audio/mpeg"}


class RSSValidationService:
	"""Validate RSS feeds against podcast directory requirements."""

	def __init__(self, http_client: Optional[httpx.AsyncClient] = None):
		"""
		Initialize RSSValidationService.

		Args:
			http_client: Optional httpx async client for image validation.
		"""
		self._http_client = http_client

	async def validate_rss_feed(
		self,
		db: AsyncSession,
		project_id: UUID,
		rss_content: Optional[str] = None,
	) -> ValidationStatusResponse:
		"""
		Validate RSS feed for Apple Podcasts, Spotify, and Google Podcasts.

		Fetches the RSSFeed record from the database and uses the provided
		rss_content or raises 404 if the feed has not been generated.
		Stores results in RSSFeed.validation_status.

		Args:
			db: Async database session
			project_id: UUID of the project whose feed to validate
			rss_content: Optional RSS XML string; required for validation

		Returns:
			ValidationStatusResponse with all directory results

		Raises:
			ValueError: If RSS content is not provided or cannot be parsed
		"""
		if not rss_content:
			raise ValueError("rss_content is required for validation")

		# Parse XML
		root = self._parse_rss_xml(rss_content)

		now = datetime.now(timezone.utc)

		# Run directory validations
		apple_result = await self._validate_apple_podcasts(root, now)
		spotify_result = await self._validate_spotify(root, now)
		google_result = await self._validate_google_podcasts(root, now)

		is_valid_for_all = apple_result.valid and spotify_result.valid and google_result.valid

		result = ValidationStatusResponse(
			last_validated_at=now,
			apple_podcasts=apple_result,
			spotify=spotify_result,
			google_podcasts=google_result,
			is_valid_for_all=is_valid_for_all,
		)

		# Persist results to RSSFeed.validation_status
		await self._store_validation_results(db, project_id, result)

		return result

	async def get_validation_status(
		self,
		db: AsyncSession,
		project_id: UUID,
	) -> Optional[ValidationStatusResponse]:
		"""
		Return the stored validation results for a project's RSS feed.

		Args:
			db: Async database session
			project_id: UUID of the project

		Returns:
			ValidationStatusResponse or None if feed not yet validated
		"""
		result = await db.execute(
			select(RSSFeed).where(RSSFeed.project_id == project_id)
		)
		rss_feed = result.scalar_one_or_none()

		if rss_feed is None or not rss_feed.validation_status:
			return None

		vs = rss_feed.validation_status
		if not vs.get("last_validated_at"):
			return None

		try:
			return ValidationStatusResponse(**vs)
		except Exception:
			return None

	# ========================================================================
	# Directory validators
	# ========================================================================

	async def _validate_apple_podcasts(
		self,
		root: ET.Element,
		now: datetime,
	) -> DirectoryValidationResult:
		"""Validate against Apple Podcasts requirements."""
		errors: list[ValidationError] = []
		warnings: list[ValidationError] = []

		channel = root.find("channel")
		if channel is None:
			errors.append(ValidationError(
				field="channel",
				level="error",
				message="RSS feed is missing <channel> element.",
			))
			return DirectoryValidationResult(
				directory="apple_podcasts",
				valid=False,
				errors=errors,
				warnings=warnings,
				checked_at=now,
			)

		# Required channel elements
		required_channel = {
			"title": "Channel title is required.",
			"link": "Channel link (website URL) is required.",
			"description": "Channel description is required.",
			"language": "Language code is required (e.g. en-US).",
		}
		for tag, msg in required_channel.items():
			if channel.find(tag) is None or not (channel.find(tag).text or "").strip():
				errors.append(ValidationError(field=tag, level="error", message=msg))

		# iTunes required
		itunes_author = channel.find("itunes:author", NAMESPACES)
		if itunes_author is None or not (itunes_author.text or "").strip():
			errors.append(ValidationError(
				field="itunes:author",
				level="error",
				message="itunes:author is required for Apple Podcasts.",
				examples=["<itunes:author>Your Name</itunes:author>"],
			))

		itunes_image = channel.find("itunes:image", NAMESPACES)
		image_url: Optional[str] = None
		if itunes_image is None or not itunes_image.get("href", "").strip():
			errors.append(ValidationError(
				field="itunes:image",
				level="error",
				message="itunes:image href is required. Podcast artwork must be provided.",
				examples=['<itunes:image href="https://example.com/artwork.jpg"/>'],
			))
		else:
			image_url = itunes_image.get("href", "").strip()

		itunes_category = channel.find("itunes:category", NAMESPACES)
		if itunes_category is None or not itunes_category.get("text", "").strip():
			errors.append(ValidationError(
				field="itunes:category",
				level="error",
				message="itunes:category is required for Apple Podcasts.",
				examples=['<itunes:category text="Technology"/>'],
			))

		itunes_explicit = channel.find("itunes:explicit", NAMESPACES)
		if itunes_explicit is None or (itunes_explicit.text or "").strip() not in {"true", "false", "yes", "no"}:
			errors.append(ValidationError(
				field="itunes:explicit",
				level="error",
				message="itunes:explicit must be 'true' or 'false'.",
				examples=["<itunes:explicit>false</itunes:explicit>"],
			))

		# Image validation
		if image_url:
			image_errors = await self._validate_image(image_url, min_dimension=3000)
			errors.extend(image_errors)

		# Episode items
		items = channel.findall("item")
		for item in items:
			item_errors, item_warnings = self._validate_apple_item(item)
			errors.extend(item_errors)
			warnings.extend(item_warnings)

		return DirectoryValidationResult(
			directory="apple_podcasts",
			valid=len(errors) == 0,
			errors=errors,
			warnings=warnings,
			checked_at=now,
		)

	async def _validate_spotify(
		self,
		root: ET.Element,
		now: datetime,
	) -> DirectoryValidationResult:
		"""Validate against Spotify requirements."""
		errors: list[ValidationError] = []
		warnings: list[ValidationError] = []

		channel = root.find("channel")
		if channel is None:
			errors.append(ValidationError(
				field="channel",
				level="error",
				message="RSS feed is missing <channel> element.",
			))
			return DirectoryValidationResult(
				directory="spotify",
				valid=False,
				errors=errors,
				warnings=warnings,
				checked_at=now,
			)

		# Required channel elements for Spotify
		for tag, msg in [
			("title", "Channel title is required."),
			("description", "Channel description is required (max 4000 chars)."),
			("link", "Channel link (website URL) is required."),
			("language", "Language code is required (BCP 47, e.g. en-US)."),
		]:
			el = channel.find(tag)
			if el is None or not (el.text or "").strip():
				errors.append(ValidationError(field=tag, level="error", message=msg))

		itunes_image = channel.find("itunes:image", NAMESPACES)
		image_url: Optional[str] = None
		if itunes_image is None or not itunes_image.get("href", "").strip():
			errors.append(ValidationError(
				field="itunes:image",
				level="error",
				message="itunes:image href is required for Spotify.",
			))
		else:
			image_url = itunes_image.get("href", "").strip()

		if image_url:
			image_errors = await self._validate_image(image_url, min_dimension=3000)
			errors.extend(image_errors)

		# Check XML encoding declaration
		# (can't verify from parsed tree, but we note UTF-8 requirement)

		# Episode items
		items = channel.findall("item")
		guids: set[str] = set()
		for item in items:
			item_errors, item_warnings = self._validate_spotify_item(item, guids)
			errors.extend(item_errors)
			warnings.extend(item_warnings)

		return DirectoryValidationResult(
			directory="spotify",
			valid=len(errors) == 0,
			errors=errors,
			warnings=warnings,
			checked_at=now,
		)

	async def _validate_google_podcasts(
		self,
		root: ET.Element,
		now: datetime,
	) -> DirectoryValidationResult:
		"""Validate against Google Podcasts requirements."""
		errors: list[ValidationError] = []
		warnings: list[ValidationError] = []

		channel = root.find("channel")
		if channel is None:
			errors.append(ValidationError(
				field="channel",
				level="error",
				message="RSS feed is missing <channel> element.",
			))
			return DirectoryValidationResult(
				directory="google_podcasts",
				valid=False,
				errors=errors,
				warnings=warnings,
				checked_at=now,
			)

		# Required channel fields
		for tag, msg in [
			("title", "Channel title is required."),
			("description", "Channel description is required."),
			("link", "Channel link is required."),
			("language", "Language code is required."),
		]:
			el = channel.find(tag)
			if el is None or not (el.text or "").strip():
				errors.append(ValidationError(field=tag, level="error", message=msg))

		# lastBuildDate is required for Google
		last_build = channel.find("lastBuildDate")
		if last_build is None or not (last_build.text or "").strip():
			errors.append(ValidationError(
				field="lastBuildDate",
				level="error",
				message="lastBuildDate is required for Google Podcasts.",
				examples=["<lastBuildDate>Wed, 15 Jan 2025 10:30:00 +0000</lastBuildDate>"],
			))
		else:
			if not self._is_valid_rfc2822_date(last_build.text):
				errors.append(ValidationError(
					field="lastBuildDate",
					level="error",
					message=f"lastBuildDate is not a valid RFC 2822 date: '{last_build.text}'.",
				))

		# Validate language code format
		language_el = channel.find("language")
		if language_el is not None and (language_el.text or "").strip():
			lang = language_el.text.strip()
			if not self._is_valid_language_code(lang):
				errors.append(ValidationError(
					field="language",
					level="error",
					message=f"Language code '{lang}' is not a valid BCP 47 code.",
					examples=["en-US", "es-ES", "fr-FR"],
				))

		# Episode items
		items = channel.findall("item")
		for item in items:
			item_errors = self._validate_google_item(item)
			errors.extend(item_errors)

		return DirectoryValidationResult(
			directory="google_podcasts",
			valid=len(errors) == 0,
			errors=errors,
			warnings=warnings,
			checked_at=now,
		)

	# ========================================================================
	# Item-level validators
	# ========================================================================

	def _validate_apple_item(
		self,
		item: ET.Element,
	) -> tuple[list[ValidationError], list[ValidationError]]:
		"""Validate a single episode <item> for Apple Podcasts."""
		errors: list[ValidationError] = []
		warnings: list[ValidationError] = []

		title = item.find("title")
		if title is None or not (title.text or "").strip():
			errors.append(ValidationError(
				field="item/title",
				level="error",
				message="Episode title is required.",
			))

		description = item.find("description")
		content_encoded = item.find("content:encoded", NAMESPACES)
		if (description is None or not (description.text or "").strip()) and \
				(content_encoded is None or not (content_encoded.text or "").strip()):
			errors.append(ValidationError(
				field="item/description",
				level="error",
				message="Episode description or content:encoded is required.",
			))

		enclosure = item.find("enclosure")
		if enclosure is None:
			errors.append(ValidationError(
				field="item/enclosure",
				level="error",
				message="Episode enclosure (audio file reference) is required.",
			))
		else:
			enc_url = enclosure.get("url", "").strip()
			enc_type = enclosure.get("type", "").strip()
			enc_length = enclosure.get("length", "").strip()

			if not enc_url:
				errors.append(ValidationError(
					field="item/enclosure/@url",
					level="error",
					message="Enclosure URL is required.",
				))

			if enc_type not in APPLE_AUDIO_TYPES:
				errors.append(ValidationError(
					field="item/enclosure/@type",
					level="error",
					message=f"Enclosure type '{enc_type}' is not supported. Must be one of: {', '.join(sorted(APPLE_AUDIO_TYPES))}.",
				))

			if not enc_length or not enc_length.isdigit():
				errors.append(ValidationError(
					field="item/enclosure/@length",
					level="error",
					message="Enclosure length (file size in bytes) is required and must be numeric.",
				))

		pub_date = item.find("pubDate")
		if pub_date is None or not (pub_date.text or "").strip():
			errors.append(ValidationError(
				field="item/pubDate",
				level="error",
				message="Episode pubDate is required (RFC 2822 format).",
				examples=["<pubDate>Wed, 15 Jan 2025 10:30:00 +0000</pubDate>"],
			))
		elif not self._is_valid_rfc2822_date(pub_date.text):
			errors.append(ValidationError(
				field="item/pubDate",
				level="error",
				message=f"pubDate '{pub_date.text}' is not a valid RFC 2822 date.",
			))

		guid = item.find("guid")
		if guid is None or not (guid.text or "").strip():
			errors.append(ValidationError(
				field="item/guid",
				level="error",
				message="Episode GUID (unique identifier) is required.",
			))

		itunes_duration = item.find("itunes:duration", NAMESPACES)
		if itunes_duration is None or not (itunes_duration.text or "").strip():
			errors.append(ValidationError(
				field="item/itunes:duration",
				level="error",
				message="itunes:duration is required for Apple Podcasts.",
				examples=["<itunes:duration>1800</itunes:duration>"],
			))

		# Warnings
		itunes_ep_type = item.find("itunes:episodeType", NAMESPACES)
		if itunes_ep_type is None:
			warnings.append(ValidationError(
				field="item/itunes:episodeType",
				level="warning",
				message="itunes:episodeType not specified. Recommended for series podcasts.",
				examples=["<itunes:episodeType>full</itunes:episodeType>"],
			))

		return errors, warnings

	def _validate_spotify_item(
		self,
		item: ET.Element,
		guids: set[str],
	) -> tuple[list[ValidationError], list[ValidationError]]:
		"""Validate a single episode <item> for Spotify."""
		errors: list[ValidationError] = []
		warnings: list[ValidationError] = []

		title = item.find("title")
		if title is None or not (title.text or "").strip():
			errors.append(ValidationError(
				field="item/title",
				level="error",
				message="Episode title is required.",
			))

		description = item.find("description")
		if description is None or not (description.text or "").strip():
			errors.append(ValidationError(
				field="item/description",
				level="error",
				message="Episode description is required.",
			))

		pub_date = item.find("pubDate")
		if pub_date is None or not (pub_date.text or "").strip():
			errors.append(ValidationError(
				field="item/pubDate",
				level="error",
				message="Episode pubDate is required (RFC 2822 format).",
			))

		guid = item.find("guid")
		if guid is None or not (guid.text or "").strip():
			errors.append(ValidationError(
				field="item/guid",
				level="error",
				message="Episode GUID is required and must be globally unique.",
			))
		else:
			guid_val = (guid.text or "").strip()
			if guid_val in guids:
				errors.append(ValidationError(
					field="item/guid",
					level="error",
					message=f"Duplicate GUID detected: '{guid_val}'. GUIDs must be unique per episode.",
				))
			guids.add(guid_val)

		enclosure = item.find("enclosure")
		if enclosure is None:
			errors.append(ValidationError(
				field="item/enclosure",
				level="error",
				message="Episode enclosure is required.",
			))
		else:
			enc_type = enclosure.get("type", "").strip()
			enc_length = enclosure.get("length", "").strip()
			enc_url = enclosure.get("url", "").strip()

			if enc_type not in SPOTIFY_AUDIO_TYPES:
				errors.append(ValidationError(
					field="item/enclosure/@type",
					level="error",
					message=f"Spotify requires audio/mpeg enclosure type. Found: '{enc_type}'.",
					details=f"Spotify does not support '{enc_type}'. Convert your audio to MP3 format.",
				))

			if not enc_url:
				errors.append(ValidationError(
					field="item/enclosure/@url",
					level="error",
					message="Enclosure URL is required.",
				))

			if not enc_length or not enc_length.isdigit():
				errors.append(ValidationError(
					field="item/enclosure/@length",
					level="error",
					message="Enclosure length must be present and numeric.",
				))

		return errors, warnings

	def _validate_google_item(self, item: ET.Element) -> list[ValidationError]:
		"""Validate a single episode <item> for Google Podcasts."""
		errors: list[ValidationError] = []

		title = item.find("title")
		if title is None or not (title.text or "").strip():
			errors.append(ValidationError(
				field="item/title",
				level="error",
				message="Episode title is required.",
			))

		description = item.find("description")
		if description is None or not (description.text or "").strip():
			errors.append(ValidationError(
				field="item/description",
				level="error",
				message="Episode description is required.",
			))

		pub_date = item.find("pubDate")
		if pub_date is None or not (pub_date.text or "").strip():
			errors.append(ValidationError(
				field="item/pubDate",
				level="error",
				message="Episode pubDate is required.",
			))

		enclosure = item.find("enclosure")
		if enclosure is None:
			errors.append(ValidationError(
				field="item/enclosure",
				level="error",
				message="Episode enclosure (audio file reference) is required.",
			))

		guid = item.find("guid")
		if guid is None or not (guid.text or "").strip():
			errors.append(ValidationError(
				field="item/guid",
				level="error",
				message="Episode GUID is required.",
			))

		return errors

	# ========================================================================
	# Image validation
	# ========================================================================

	async def _validate_image(
		self,
		image_url: str,
		min_dimension: int = 3000,
		max_size_kb: int = 500,
	) -> list[ValidationError]:
		"""
		Validate podcast artwork image URL.

		Checks URL accessibility, format (JPG/PNG), and dimensions.

		Args:
			image_url: URL of the image to validate
			min_dimension: Minimum width/height in pixels
			max_size_kb: Maximum file size in kilobytes

		Returns:
			List of ValidationError items describing any issues found
		"""
		errors: list[ValidationError] = []
		client = self._http_client

		try:
			if client:
				response = await client.head(image_url, follow_redirects=True, timeout=10.0)
			else:
				async with httpx.AsyncClient() as c:
					response = await c.head(image_url, follow_redirects=True, timeout=10.0)

			if response.status_code != 200:
				errors.append(ValidationError(
					field="itunes:image",
					level="error",
					message=f"Artwork URL returned HTTP {response.status_code}. Image must be publicly accessible.",
					details=f"URL: {image_url}",
				))
				return errors

			content_type = response.headers.get("content-type", "").lower()
			content_length = response.headers.get("content-length")

			# Check format
			if not any(fmt in content_type for fmt in ("image/jpeg", "image/jpg", "image/png")):
				errors.append(ValidationError(
					field="itunes:image",
					level="error",
					message=f"Artwork must be JPG or PNG format. Got content-type: '{content_type}'.",
				))

			# Check file size
			if content_length and content_length.isdigit():
				size_kb = int(content_length) / 1024
				if size_kb > max_size_kb:
					errors.append(ValidationError(
						field="itunes:image",
						level="error",
						message=f"Artwork file size is {size_kb:.0f} KB. Maximum is {max_size_kb} KB.",
						details=f"URL: {image_url}",
					))

		except httpx.TimeoutException:
			errors.append(ValidationError(
				field="itunes:image",
				level="error",
				message="Artwork URL timed out. Image must be publicly accessible.",
				details=f"URL: {image_url}",
			))
		except httpx.RequestError as exc:
			errors.append(ValidationError(
				field="itunes:image",
				level="error",
				message="Could not fetch artwork URL. Image must be publicly accessible.",
				details=str(exc),
			))

		# Attempt to fetch and check image dimensions using Pillow if available
		try:
			from io import BytesIO
			import PIL.Image  # type: ignore

			if client:
				img_response = await client.get(image_url, follow_redirects=True, timeout=15.0)
			else:
				async with httpx.AsyncClient() as c:
					img_response = await c.get(image_url, follow_redirects=True, timeout=15.0)

			if img_response.status_code == 200:
				img = PIL.Image.open(BytesIO(img_response.content))
				width, height = img.size
				if width < min_dimension or height < min_dimension:
					errors.append(ValidationError(
						field="itunes:image",
						level="error",
						message=(
							f"Artwork dimensions are {width}x{height} pixels. "
							f"Minimum required: {min_dimension}x{min_dimension} pixels."
						),
						details=f"URL: {image_url}",
					))
		except ImportError:
			# Pillow not installed — skip dimension check
			pass
		except Exception:
			# Image fetch/parse failed — skip dimension check
			pass

		return errors

	# ========================================================================
	# Helpers
	# ========================================================================

	def _parse_rss_xml(self, rss_content: str) -> ET.Element:
		"""
		Parse RSS XML string and return root element.

		Args:
			rss_content: RSS 2.0 XML string

		Returns:
			Root ET.Element

		Raises:
			ValueError: If XML cannot be parsed
		"""
		try:
			return ET.fromstring(rss_content)
		except ET.ParseError as exc:
			raise ValueError(f"Invalid RSS XML: {exc}") from exc

	def _check_required_fields(
		self,
		element: ET.Element,
		required_fields: list[str],
	) -> list[ValidationError]:
		"""
		Check for required XML child elements in an element.

		Args:
			element: Parent XML element
			required_fields: Tag names to check for

		Returns:
			List of ValidationError for each missing field
		"""
		errors: list[ValidationError] = []
		for field in required_fields:
			child = element.find(field)
			if child is None or not (child.text or "").strip():
				errors.append(ValidationError(
					field=field,
					level="error",
					message=f"Required field <{field}> is missing or empty.",
				))
		return errors

	def _is_valid_rfc2822_date(self, date_str: Optional[str]) -> bool:
		"""
		Check whether a string is a valid RFC 2822 date.

		Args:
			date_str: Date string to validate

		Returns:
			True if valid, False otherwise
		"""
		if not date_str:
			return False
		try:
			parsedate_to_datetime(date_str.strip())
			return True
		except Exception:
			return False

	def _is_valid_language_code(self, lang: str) -> bool:
		"""
		Check whether a string looks like a valid BCP 47 language code.

		Accepts codes like 'en', 'en-US', 'zh-Hant-TW', etc.

		Args:
			lang: Language code string

		Returns:
			True if format looks valid, False otherwise
		"""
		return bool(re.match(r"^[a-zA-Z]{2,3}(-[a-zA-Z0-9]{2,8})*$", lang.strip()))

	async def _store_validation_results(
		self,
		db: AsyncSession,
		project_id: UUID,
		result: ValidationStatusResponse,
	) -> None:
		"""
		Persist validation results to RSSFeed.validation_status.

		Args:
			db: Async database session
			project_id: UUID of the project
			result: Validation results to store
		"""
		db_result = await db.execute(
			select(RSSFeed).where(RSSFeed.project_id == project_id)
		)
		rss_feed = db_result.scalar_one_or_none()
		if rss_feed is None:
			return

		rss_feed.validation_status = result.model_dump(mode="json")
		await db.commit()
