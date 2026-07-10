"""Tenant offboarding service — GDPR-style account erasure (issue #308)."""

import logging

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.audio_snippet import AudioSnippet
from ..models.content_source import ContentSource
from ..models.episode import Episode
from ..models.episode_composition import EpisodeComposition
from ..models.project import Project
from ..models.rss_feed import RSSFeed
from ..models.storage_deletion_outbox import StorageDeletionOutbox
from ..models.user import User
from ..tasks.maintenance import drain_storage_deletion_outbox

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
	compositions, audio snippets, RSS feeds, and content sources, then queues
	each onto the durable storage_deletion_outbox in the same transaction as
	the user row delete (issue #366) instead of deleting from storage inline —
	a commit failure therefore leaves storage untouched. The GC worker
	(drain_storage_deletion_outbox) performs the actual deletion, retrying
	until it succeeds; a best-effort post-commit trigger below makes that
	happen promptly instead of waiting for the next beat tick. Every tenant row
	(billing rows included — see migration 010) cascades via `ON DELETE
	CASCADE` once the user row itself is deleted.

	Args:
		db: Database session (tenant context must already be armed for this user)
		user: User instance to erase

	Returns:
		Summary dict with counts of S3 objects and local files queued for deletion

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

	for key in s3_keys:
		db.add(StorageDeletionOutbox(tenant_id=user.tenant_id, s3_key=key))
	for path in local_paths:
		db.add(StorageDeletionOutbox(tenant_id=user.tenant_id, file_path=path))

	# Core DELETE (not ORM db.delete) so the ORM doesn't load and walk the full
	# relationship graph — Postgres ON DELETE CASCADE removes the child rows.
	# That includes billing_subscriptions/billing_usage: their ORM models omit
	# the FK, but migration 010 created user_id FKs with ON DELETE CASCADE.
	await db.execute(delete(User).where(User.id == user.id))

	# Audit record of the erasure, emitted before commit — after commit the user
	# row is gone and this log line is the only durable trace of what happened.
	logger.info(
		"account erasure: user=%s tenant=%s s3_queued=%d local_queued=%d",
		user.id,
		user.tenant_id,
		len(s3_keys),
		len(local_paths),
	)
	await db.commit()

	if s3_keys or local_paths:
		try:
			drain_storage_deletion_outbox.delay()
		except Exception:
			logger.warning(f"Failed to trigger storage deletion drain for user {user.id}")

	return {
		"s3_objects_queued": len(s3_keys),
		"local_files_queued": len(local_paths),
	}
