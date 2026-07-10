"""Tenant offboarding service — GDPR-style account erasure (issue #308)."""

import logging
import os

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.audio_snippet import AudioSnippet
from ..models.content_source import ContentSource
from ..models.episode import Episode
from ..models.episode_composition import EpisodeComposition
from ..models.project import Project
from ..models.rss_feed import RSSFeed
from ..models.user import User
from .storage_service import StorageService

logger = logging.getLogger(__name__)

# Generation-pipeline states during which erasure is refused: a Celery chain is
# still running and would re-upload audio to S3 after we deleted it, recreating
# the orphaned-object problem this service exists to fix (issue #308).
ACTIVE_GENERATION_STATUSES = {"queued", "generating", "composing", "uploading", "distributing"}


async def erase_user(db: AsyncSession, user: User) -> dict:
	"""
	Permanently erase a user's account: Postgres rows, S3 audio objects, and
	local file artifacts (GDPR-style tenant offboarding / right to erasure).

	Collects S3 keys and local paths from the user's episodes, episode
	compositions, audio snippets, RSS feeds, and content sources, then
	best-effort deletes each — failures are logged but never block erasure.
	Every tenant row (billing rows included — see migration 010) cascades via
	`ON DELETE CASCADE` once the user row itself is deleted.

	Args:
		db: Database session (tenant context must already be armed for this user)
		user: User instance to erase

	Returns:
		Summary dict with counts of S3 objects and local files erased

	Raises:
		HTTPException: 409 if any of the user's episodes is still generating
	"""
	active_count = await db.scalar(
		select(func.count())
		.select_from(Episode)
		.where(
			Episode.user_id == user.id,
			Episode.generation_status.in_(ACTIVE_GENERATION_STATUSES),
		)
	)
	if active_count:
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail=(
				f"{active_count} episode(s) are still generating; "
				"wait for them to finish (or fail) before deleting the account"
			),
		)

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

	failed_keys = []
	if s3_keys:
		storage = StorageService()
		for key in s3_keys:
			try:
				await storage.delete_file(key)
			except Exception:
				failed_keys.append(key)
				logger.warning(f"Failed to delete S3 object {key} for user {user.id}")

	failed_paths = []
	for path in local_paths:
		try:
			os.remove(path)
		except OSError:
			failed_paths.append(path)
			logger.warning(f"Failed to remove local file {path} for user {user.id}")

	# Core DELETE (not ORM db.delete) so the ORM doesn't load and walk the full
	# relationship graph — Postgres ON DELETE CASCADE removes the child rows.
	# That includes billing_subscriptions/billing_usage: their ORM models omit
	# the FK, but migration 010 created user_id FKs with ON DELETE CASCADE.
	await db.execute(delete(User).where(User.id == user.id))

	# Audit record of the erasure, emitted before commit — after commit the user
	# row is gone and this log line is the only durable trace of what happened.
	logger.info(
		"account erasure: user=%s tenant=%s s3_deleted=%d s3_failed=%s "
		"local_deleted=%d local_failed=%s",
		user.id,
		user.tenant_id,
		len(s3_keys) - len(failed_keys),
		failed_keys or "none",
		len(local_paths) - len(failed_paths),
		failed_paths or "none",
	)
	await db.commit()

	return {
		"s3_objects_deleted": len(s3_keys) - len(failed_keys),
		"local_files_deleted": len(local_paths) - len(failed_paths),
	}
