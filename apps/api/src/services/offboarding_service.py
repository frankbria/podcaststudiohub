"""Tenant offboarding service — GDPR-style account erasure (issue #308)."""

import logging
import os

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.audio_snippet import AudioSnippet
from ..models.billing_subscription import BillingSubscription
from ..models.billing_usage import BillingUsage
from ..models.content_source import ContentSource
from ..models.episode import Episode
from ..models.episode_composition import EpisodeComposition
from ..models.project import Project
from ..models.rss_feed import RSSFeed
from ..models.user import User
from .storage_service import StorageService

logger = logging.getLogger(__name__)


async def erase_user(db: AsyncSession, user: User) -> dict:
	"""
	Permanently erase a user's account: Postgres rows, S3 audio objects, and
	local file artifacts (GDPR-style tenant offboarding / right to erasure).

	Collects S3 keys and local paths from the user's episodes, episode
	compositions, audio snippets, RSS feeds, and content sources, then
	best-effort deletes each — failures are logged but never block erasure.
	BillingSubscription/BillingUsage rows have no FK to users and are deleted
	explicitly; every other tenant row cascades via `ON DELETE CASCADE` once
	the user row itself is deleted.

	Args:
		db: Database session (tenant context must already be armed for this user)
		user: User instance to erase

	Returns:
		Summary dict with counts of S3 objects and local files erased
	"""
	projects_result = await db.execute(select(Project.id).where(Project.user_id == user.id))
	project_ids = [row[0] for row in projects_result.all()]

	episodes_result = await db.execute(select(Episode).where(Episode.user_id == user.id))
	episodes = episodes_result.scalars().all()
	episode_ids = [episode.id for episode in episodes]

	compositions = []
	content_sources = []
	if episode_ids:
		compositions_result = await db.execute(
			select(EpisodeComposition).where(EpisodeComposition.episode_id.in_(episode_ids))
		)
		compositions = compositions_result.scalars().all()

		content_sources_result = await db.execute(
			select(ContentSource).where(ContentSource.episode_id.in_(episode_ids))
		)
		content_sources = content_sources_result.scalars().all()

	snippets_result = await db.execute(select(AudioSnippet).where(AudioSnippet.user_id == user.id))
	snippets = snippets_result.scalars().all()

	rss_feeds = []
	if project_ids:
		rss_feeds_result = await db.execute(select(RSSFeed).where(RSSFeed.project_id.in_(project_ids)))
		rss_feeds = rss_feeds_result.scalars().all()

	s3_keys = []
	s3_keys.extend(episode.s3_key for episode in episodes if episode.s3_key)
	s3_keys.extend(composition.composed_s3_key for composition in compositions if composition.composed_s3_key)
	s3_keys.extend(snippet.s3_key for snippet in snippets if snippet.s3_key)
	s3_keys.extend(rss_feed.s3_key for rss_feed in rss_feeds if rss_feed.s3_key)
	for source in content_sources:
		key = (source.source_data or {}).get("s3_key")
		if key:
			s3_keys.append(key)

	local_paths = []
	local_paths.extend(episode.file_path for episode in episodes if episode.file_path)
	local_paths.extend(episode.transcript_path for episode in episodes if episode.transcript_path)
	local_paths.extend(
		composition.composed_file_path for composition in compositions if composition.composed_file_path
	)
	local_paths.extend(snippet.file_path for snippet in snippets if snippet.file_path)

	for key in s3_keys:
		try:
			storage = StorageService()
			await storage.delete_file(key)
		except Exception:
			logger.warning(f"Failed to delete S3 object {key} for user {user.id}")

	for path in local_paths:
		try:
			os.remove(path)
		except OSError:
			logger.warning(f"Failed to remove local file {path} for user {user.id}")

	# Billing rows have no FK to users, so DB cascade won't reach them.
	await db.execute(delete(BillingSubscription).where(BillingSubscription.user_id == user.id))
	await db.execute(delete(BillingUsage).where(BillingUsage.user_id == user.id))

	await db.delete(user)
	await db.commit()

	return {
		"s3_objects_deleted": len(s3_keys),
		"local_files_deleted": len(local_paths),
	}
