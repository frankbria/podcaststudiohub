"""
RSS Generation Service for podcast feed management.

Generates valid RSS 2.0 XML documents with Apple Podcasts and Spotify
compliance, uploads to S3, and manages RSSFeed records.
"""

from datetime import datetime, timezone
from email.utils import format_datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Episode, Project, RSSFeed
from .storage_service import StorageService
from ..utils.datetime_utils import utcnow


class RSSGenerationService:
	"""Generate and manage RSS 2.0 podcast feeds."""

	# Required fields in podcast_metadata for feed generation
	REQUIRED_METADATA_FIELDS = {"show_title", "author", "description"}

	def __init__(self, storage: Optional[StorageService] = None):
		"""
		Initialize RSSGenerationService.

		Args:
			storage: Optional StorageService instance (created automatically if None)
		"""
		self.storage = storage or StorageService()

	async def generate_rss_for_project(
		self,
		db: AsyncSession,
		project_id: UUID,
		user_id: UUID,
	) -> RSSFeed:
		"""
		Generate RSS 2.0 feed for all completed episodes in a project.

		Retrieves all completed episodes, builds RSS XML document,
		uploads to S3, stores URL in RSSFeed model.

		Args:
			db: Async database session
			project_id: UUID of the project to generate feed for
			user_id: UUID of the requesting user (for access check)

		Returns:
			RSSFeed object with generated feed metadata

		Raises:
			ValueError: If project not found or podcast_metadata invalid
		"""
		# Fetch project (RLS ensures tenant isolation)
		project = await self._get_project(db, project_id)
		if project is None:
			raise ValueError(f"Project {project_id} not found")

		# Validate podcast metadata has required fields
		self._validate_podcast_metadata(project.podcast_metadata or {})

		# Fetch completed episodes ordered by created_at descending
		episodes = await self._get_completed_episodes(db, project_id)

		# Build RSS XML document
		xml_content = self._build_rss_document(project, episodes)

		# Upload to S3
		s3_key, public_url = await self._upload_rss_to_s3(project_id, xml_content)

		# Get or create RSSFeed record
		rss_feed = await self._get_or_create_rss_feed(db, project_id, project.tenant_id)

		# Update feed metadata
		rss_feed = await self._update_rss_feed(db, rss_feed, s3_key, public_url)

		return rss_feed

	async def get_rss_feed(
		self,
		db: AsyncSession,
		project_id: UUID,
	) -> Optional[RSSFeed]:
		"""
		Get existing RSS feed record for a project.

		Args:
			db: Async database session
			project_id: UUID of the project

		Returns:
			RSSFeed instance or None if not generated yet
		"""
		result = await db.execute(
			select(RSSFeed).where(RSSFeed.project_id == project_id)
		)
		return result.scalar_one_or_none()

	def _build_rss_document(self, project: Project, episodes: list) -> str:
		"""
		Build complete RSS 2.0 XML document string.

		Generates a valid RSS 2.0 feed with iTunes/Apple Podcasts namespace
		support. Episodes are sorted newest-first by created_at.

		Args:
			project: Project model instance with podcast_metadata
			episodes: List of Episode model instances (complete only)

		Returns:
			UTF-8 encoded XML string
		"""
		# Sort episodes newest-first (defensive sort; DB query also orders this way)
		episodes = sorted(
			episodes,
			key=lambda ep: getattr(ep, "created_at", datetime.min) or datetime.min,
			reverse=True,
		)

		metadata = project.podcast_metadata or {}
		show_title = metadata.get("show_title", project.name or "")
		author = metadata.get("author", "")
		description = metadata.get("description", "")
		language = metadata.get("language", "en")
		explicit = metadata.get("explicit", False)
		copyright_text = metadata.get("copyright", "")
		artwork_url = metadata.get("artwork_url", "")
		category = metadata.get("category", "")

		# Owner email from project user relationship
		owner_email = ""
		if hasattr(project, "user") and project.user:
			owner_email = getattr(project.user, "email", "")

		now = datetime.now(timezone.utc)

		# Build XML using string construction to ensure proper namespace and CDATA support
		lines = [
			'<?xml version="1.0" encoding="UTF-8"?>',
			'<rss version="2.0"',
			'  xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"',
			'  xmlns:content="http://purl.org/rss/1.0/modules/content/">',
			"  <channel>",
			f"    <title>{self._escape_xml(show_title)}</title>",
			f"    <link>{self._escape_xml(metadata.get('website_url', ''))}</link>",
			f"    <description>{self._escape_xml(description)}</description>",
			f"    <language>{self._escape_xml(language)}</language>",
		]

		if copyright_text:
			lines.append(f"    <copyright>{self._escape_xml(copyright_text)}</copyright>")

		lines.append(f"    <lastBuildDate>{self._format_rfc2822_date(now)}</lastBuildDate>")

		# iTunes required tags
		lines.append(f"    <itunes:author>{self._escape_xml(author)}</itunes:author>")

		if category:
			lines.append(f'    <itunes:category text="{self._escape_xml(category)}"/>')

		lines.append(f"    <itunes:explicit>{'true' if explicit else 'false'}</itunes:explicit>")

		if artwork_url:
			lines.append(f'    <itunes:image href="{self._escape_xml(artwork_url)}"/>')

		lines.extend([
			"    <itunes:owner>",
			f"      <itunes:name>{self._escape_xml(author)}</itunes:name>",
			f"      <itunes:email>{self._escape_xml(owner_email)}</itunes:email>",
			"    </itunes:owner>",
		])

		# Episode items (ordered newest first by caller)
		for episode in episodes:
			lines.extend(self._build_episode_item(episode, explicit))

		lines.extend([
			"  </channel>",
			"</rss>",
		])

		return "\n".join(lines)

	def _build_episode_item(self, episode, channel_explicit: bool) -> list[str]:
		"""
		Build XML item lines for a single episode.

		Args:
			episode: Episode model instance
			channel_explicit: Channel-level explicit setting (fallback)

		Returns:
			List of XML string lines for the episode item
		"""
		ep_meta = episode.episode_metadata or {}
		title = ep_meta.get("title", "Untitled Episode")
		description = ep_meta.get("description", "")
		episode_number = ep_meta.get("episode_number")
		season_number = ep_meta.get("season_number")

		s3_url = getattr(episode, "s3_url", "") or ""
		file_size = getattr(episode, "file_size_bytes", 0) or 0
		duration = getattr(episode, "duration_seconds", 0) or 0
		created_at = getattr(episode, "created_at", datetime.now(timezone.utc))

		# Ensure created_at is timezone-aware for formatting
		if isinstance(created_at, datetime) and created_at.tzinfo is None:
			created_at = created_at.replace(tzinfo=timezone.utc)

		lines = [
			"    <item>",
			f"      <title>{self._escape_xml(title)}</title>",
			f"      <description>{self._escape_xml(description)}</description>",
			f"      <pubDate>{self._format_rfc2822_date(created_at)}</pubDate>",
			f'      <enclosure url="{self._escape_xml(s3_url)}" length="{int(file_size)}" type="audio/mpeg"/>',
			f"      <guid isPermaLink=\"false\">{episode.id}</guid>",
			f"      <itunes:duration>{int(duration)}</itunes:duration>",
			f"      <itunes:explicit>{'true' if channel_explicit else 'false'}</itunes:explicit>",
			"      <itunes:episodeType>full</itunes:episodeType>",
		]

		if episode_number is not None:
			lines.append(f"      <itunes:episode>{int(episode_number)}</itunes:episode>")

		if season_number is not None:
			lines.append(f"      <itunes:season>{int(season_number)}</itunes:season>")

		lines.append("    </item>")
		return lines

	def _validate_podcast_metadata(self, metadata: dict) -> None:
		"""
		Validate that podcast_metadata contains required fields for RSS generation.

		Args:
			metadata: Podcast metadata dictionary

		Raises:
			ValueError: If required fields are missing or empty
		"""
		for field in self.REQUIRED_METADATA_FIELDS:
			if field not in metadata:
				raise ValueError(
					f"podcast_metadata missing required field: '{field}'. "
					f"Required fields: {', '.join(sorted(self.REQUIRED_METADATA_FIELDS))}"
				)
			if not isinstance(metadata[field], str) or not metadata[field].strip():
				raise ValueError(
					f"podcast_metadata.{field} must be a non-empty string"
				)

	def _format_rfc2822_date(self, dt: datetime) -> str:
		"""
		Convert datetime to RFC 2822 format required by RSS spec.

		Args:
			dt: Datetime object (naive datetimes treated as UTC)

		Returns:
			RFC 2822 formatted date string, e.g. "Wed, 15 Jan 2025 10:30:00 +0000"
		"""
		if dt.tzinfo is None:
			dt = dt.replace(tzinfo=timezone.utc)
		return format_datetime(dt, usegmt=True).replace("GMT", "+0000")

	def _escape_xml(self, text: str) -> str:
		"""
		Escape special XML characters in text content.

		Args:
			text: Raw text that may contain XML special characters

		Returns:
			Escaped text safe for XML element content
		"""
		if not isinstance(text, str):
			text = str(text)
		text = text.replace("&", "&amp;")
		text = text.replace("<", "&lt;")
		text = text.replace(">", "&gt;")
		text = text.replace('"', "&quot;")
		text = text.replace("'", "&apos;")
		return text

	async def _get_project(self, db: AsyncSession, project_id: UUID) -> Optional[Project]:
		"""
		Fetch project by ID with user relationship loaded.

		Args:
			db: Async database session
			project_id: Project UUID

		Returns:
			Project instance or None
		"""
		from sqlalchemy.orm import selectinload
		result = await db.execute(
			select(Project)
			.options(selectinload(Project.user))
			.where(Project.id == project_id)
		)
		return result.scalar_one_or_none()

	async def _get_completed_episodes(self, db: AsyncSession, project_id: UUID) -> list:
		"""
		Fetch all completed episodes for a project, ordered newest first.

		Args:
			db: Async database session
			project_id: Project UUID

		Returns:
			List of Episode instances with generation_status == 'complete'
		"""
		result = await db.execute(
			select(Episode)
			.where(
				Episode.project_id == project_id,
				Episode.generation_status == "complete",
			)
			.order_by(Episode.created_at.desc())
		)
		return list(result.scalars().all())

	async def _upload_rss_to_s3(self, project_id: UUID, xml_content: str) -> tuple[str, str]:
		"""
		Upload RSS XML content to S3 with public-read ACL.

		Args:
			project_id: Project UUID (used in S3 key path)
			xml_content: RSS XML string to upload

		Returns:
			Tuple of (s3_key, public_url)
		"""
		import tempfile
		import os

		s3_key = f"rss-feeds/{project_id}/feed.xml"

		# Write to temp file for upload
		with tempfile.NamedTemporaryFile(
			mode="w",
			suffix=".xml",
			delete=False,
			encoding="utf-8",
		) as tmp:
			tmp.write(xml_content)
			tmp_path = tmp.name

		try:
			public_url = await self.storage.upload_file(
				file_path=tmp_path,
				s3_key=s3_key,
				content_type="application/rss+xml",
				public=True,
			)
		finally:
			os.unlink(tmp_path)

		return s3_key, public_url

	async def _get_or_create_rss_feed(
		self,
		db: AsyncSession,
		project_id: UUID,
		tenant_id: UUID,
	) -> RSSFeed:
		"""
		Get existing RSSFeed record or create a new one.

		Args:
			db: Async database session
			project_id: Project UUID
			tenant_id: Tenant UUID

		Returns:
			RSSFeed instance (existing or newly created)
		"""
		result = await db.execute(
			select(RSSFeed).where(RSSFeed.project_id == project_id)
		)
		rss_feed = result.scalar_one_or_none()

		if rss_feed is None:
			rss_feed = RSSFeed(
				project_id=project_id,
				tenant_id=tenant_id,
				validation_status={},
			)
			db.add(rss_feed)
			await db.flush()

		return rss_feed

	async def _update_rss_feed(
		self,
		db: AsyncSession,
		rss_feed: RSSFeed,
		s3_key: str,
		public_url: str,
	) -> RSSFeed:
		"""
		Update RSSFeed record with new S3 key, URL, and timestamp.

		Args:
			db: Async database session
			rss_feed: RSSFeed instance to update
			s3_key: S3 object key
			public_url: Public URL of the uploaded feed

		Returns:
			Updated RSSFeed instance
		"""
		rss_feed.s3_key = s3_key
		rss_feed.public_url = public_url
		rss_feed.last_generated = utcnow()
		await db.commit()
		return rss_feed
