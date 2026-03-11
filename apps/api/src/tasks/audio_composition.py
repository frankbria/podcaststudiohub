"""
Celery tasks for audio snippet merging and composition
"""
import logging
import os
import tempfile
from typing import Any, Dict, List, Optional

from celery import Task

from src.worker import celery_app

logger = logging.getLogger(__name__)


def _download_from_s3(s3_url: str, dest_path: str) -> bool:
	"""
	Download a file from an S3 URL to a local path.

	Returns True on success, False on failure.
	"""
	try:
		import requests  # type: ignore[import]
		response = requests.get(s3_url, stream=True, timeout=60)
		response.raise_for_status()
		with open(dest_path, "wb") as f:
			for chunk in response.iter_content(chunk_size=8192):
				f.write(chunk)
		return True
	except Exception as exc:
		logger.warning("Failed to download %s: %s", s3_url, exc)
		return False


def _resolve_audio_file(
	segment: Dict[str, Any],
	temp_dir: str,
	idx: int,
) -> Optional[str]:
	"""
	Resolve the local file path for a timeline segment.

	Tries local file_path first, then s3_url download, then audio_source.

	Args:
		segment: Timeline segment dict with audio location fields
		temp_dir: Directory for temporary downloads
		idx: Segment index (for unique temp filenames)

	Returns:
		Local file path string, or None if resolution failed
	"""
	# 1. Use local file_path if available
	file_path = segment.get("file_path") or segment.get("audio_source")
	if file_path and os.path.isfile(file_path):
		return file_path

	# 2. Try to download from S3 URL
	s3_url = segment.get("s3_url")
	if s3_url and s3_url.startswith("http"):
		ext = os.path.splitext(s3_url.split("?")[0])[-1] or ".mp3"
		dest = os.path.join(temp_dir, f"segment_{idx}{ext}")
		if _download_from_s3(s3_url, dest):
			return dest

	return None


@celery_app.task(bind=True, name="merge_audio_snippets", time_limit=600)
def merge_audio_snippets_task(
	self: Task,
	episode_id: str,
	composition_id: str,
	timeline: List[Dict[str, Any]],
	output_path: str,
) -> Dict[str, Any]:
	"""
	Merge audio snippets according to the composition timeline.

	Enhanced version that:
	- Accepts a composition_id to update EpisodeComposition after render
	- Downloads snippets from S3 when no local file_path is available
	- Applies per-segment volume adjustments and fade in/out
	- Handles timeline gaps with silence padding
	- Updates Episode and EpisodeComposition records on completion

	Args:
		self: Celery task instance
		episode_id: UUID of the episode
		composition_id: UUID of the EpisodeComposition record to update
		timeline: List of timeline segments with audio sources and positions
		output_path: Local path for the final composed audio file

	Returns:
		Dictionary with composition results (status, paths, duration, file_size)
	"""
	temp_dir = tempfile.mkdtemp(prefix="podcastfy_composition_")

	try:
		self.update_state(
			state="PROGRESS",
			meta={
				"episode_id": episode_id,
				"composition_id": composition_id,
				"progress": 0,
				"status": "Starting audio composition...",
			},
		)

		from pydub import AudioSegment  # type: ignore[import]

		# Initialize empty audio
		final_audio = AudioSegment.empty()
		total_segments = len(timeline)

		if total_segments == 0:
			raise ValueError("Timeline is empty — nothing to compose")

		# Sort segments by position_seconds for proper ordering
		sorted_timeline = sorted(timeline, key=lambda s: s.get("position_seconds", 0.0))

		current_duration_ms = 0

		for idx, segment in enumerate(sorted_timeline):
			progress = int((idx / total_segments) * 80)  # 0-80% for processing
			self.update_state(
				state="PROGRESS",
				meta={
					"episode_id": episode_id,
					"composition_id": composition_id,
					"progress": progress,
					"status": f"Processing segment {idx + 1}/{total_segments}...",
				},
			)

			seg_type = segment.get("type", "")

			# Handle generated segment (main episode audio)
			if seg_type == "generated":
				episode_audio_path = segment.get("file_path") or segment.get("audio_source")
				if episode_audio_path and os.path.isfile(episode_audio_path):
					audio = AudioSegment.from_file(episode_audio_path)
				else:
					logger.info(
						"Skipping 'generated' segment (episode audio not available yet)"
					)
					continue
			else:
				audio_path = _resolve_audio_file(segment, temp_dir, idx)
				if audio_path is None:
					logger.warning(
						"Could not resolve audio for segment %d (type=%s), skipping",
						idx,
						seg_type,
					)
					continue
				audio = AudioSegment.from_file(audio_path)

			# Apply normalization
			if segment.get("normalize", True):
				audio = audio.normalize()

			# Apply volume scaling (linear to dB conversion)
			volume_level = float(segment.get("volume_level", 1.0))
			if volume_level != 1.0 and volume_level > 0:
				import math
				db_change = 20 * math.log10(volume_level)
				audio = audio + db_change

			# Apply fade in/out
			fade_in = int(segment.get("fade_in_ms", 0))
			fade_out = int(segment.get("fade_out_ms", 0))
			if fade_in > 0:
				audio = audio.fade_in(min(fade_in, len(audio)))
			if fade_out > 0:
				audio = audio.fade_out(min(fade_out, len(audio)))

			# Handle position-based placement with silence padding
			position_ms = int(float(segment.get("position_seconds", 0.0)) * 1000)
			if position_ms > current_duration_ms:
				silence = AudioSegment.silent(duration=position_ms - current_duration_ms)
				final_audio += silence
				current_duration_ms = position_ms

			final_audio += audio
			current_duration_ms += len(audio)

		if len(final_audio) == 0:
			raise ValueError("No audio segments could be resolved — composed audio is empty")

		self.update_state(
			state="PROGRESS",
			meta={
				"episode_id": episode_id,
				"composition_id": composition_id,
				"progress": 85,
				"status": "Exporting composed audio...",
			},
		)

		# Export final composed audio
		output_dir = os.path.dirname(output_path)
		if output_dir:
			os.makedirs(output_dir, exist_ok=True)
		final_audio.export(output_path, format="mp3", bitrate="192k")

		file_size_bytes = os.path.getsize(output_path)
		duration_seconds = len(final_audio) / 1000.0

		self.update_state(
			state="PROGRESS",
			meta={
				"episode_id": episode_id,
				"composition_id": composition_id,
				"progress": 90,
				"status": "Uploading to S3...",
			},
		)

		# Attempt S3 upload
		s3_url = _upload_composition_to_s3(
			file_path=output_path,
			episode_id=episode_id,
		)

		# Persist results to DB
		_update_db_after_render(
			composition_id=composition_id,
			episode_id=episode_id,
			composed_file_path=output_path,
			s3_url=s3_url,
			duration_seconds=duration_seconds,
			file_size_bytes=file_size_bytes,
		)

		return {
			"status": "success",
			"output_path": output_path,
			"s3_url": s3_url,
			"duration_seconds": duration_seconds,
			"file_size_bytes": file_size_bytes,
			"error": None,
		}

	except Exception as exc:
		logger.error(
			"Audio composition failed for episode %s: %s", episode_id, str(exc)
		)
		_mark_composition_failed(composition_id=composition_id, error=str(exc))
		return {
			"status": "failed",
			"output_path": None,
			"s3_url": None,
			"duration_seconds": 0,
			"file_size_bytes": 0,
			"error": str(exc),
		}
	finally:
		import shutil
		shutil.rmtree(temp_dir, ignore_errors=True)


def _upload_composition_to_s3(file_path: str, episode_id: str) -> Optional[str]:
	"""
	Upload the composed audio file to S3.

	Returns the public S3 URL, or None if S3 is not configured.
	"""
	try:
		from src.config import settings
		from src.services.storage_service import StorageService

		bucket = getattr(settings, "AWS_S3_BUCKET", None)
		if not bucket:
			return None

		import asyncio

		s3_key = f"compositions/{episode_id}/composed.mp3"
		storage = StorageService(bucket_name=bucket, region_name=settings.AWS_REGION)

		loop = asyncio.new_event_loop()
		try:
			url = loop.run_until_complete(
				storage.upload_file(
					file_path=file_path,
					s3_key=s3_key,
					content_type="audio/mpeg",
					public=True,
				)
			)
		finally:
			loop.close()

		return url
	except Exception as exc:
		logger.warning("S3 upload failed for episode %s: %s", episode_id, exc)
		return None


def _update_db_after_render(
	composition_id: str,
	episode_id: str,
	composed_file_path: str,
	s3_url: Optional[str],
	duration_seconds: float,
	file_size_bytes: int,
) -> None:
	"""
	Update EpisodeComposition and Episode records after a successful render.

	Opens a new async engine/session since this runs in a synchronous Celery worker.
	"""
	try:
		import asyncio
		from datetime import datetime
		from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
		from sqlalchemy.orm import sessionmaker
		from sqlalchemy import select
		from src.config import settings
		from src.models.episode_composition import EpisodeComposition
		from src.models.episode import Episode

		async def _do_update() -> None:
			engine = create_async_engine(settings.database_url, echo=False)
			async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

			async with async_session() as session:
				result = await session.execute(
					select(EpisodeComposition).where(
						EpisodeComposition.id == composition_id
					)
				)
				composition = result.scalar_one_or_none()
				if composition:
					composition.render_status = "complete"
					composition.render_error = None
					composition.last_rendered_at = datetime.utcnow()
					composition.composed_file_path = composed_file_path
					composition.composed_s3_url = s3_url
					composition.composed_duration_seconds = duration_seconds
					composition.composition_status = "final"

				ep_result = await session.execute(
					select(Episode).where(Episode.id == episode_id)
				)
				episode = ep_result.scalar_one_or_none()
				if episode and s3_url:
					episode.s3_url = s3_url
					episode.duration_seconds = duration_seconds
					episode.file_size_bytes = file_size_bytes
					episode.generation_status = "complete"

				await session.commit()

			await engine.dispose()

		loop = asyncio.new_event_loop()
		try:
			loop.run_until_complete(_do_update())
		finally:
			loop.close()

	except Exception as exc:
		logger.error(
			"Failed to update DB after composition render (episode=%s): %s",
			episode_id,
			exc,
		)


def _mark_composition_failed(composition_id: str, error: str) -> None:
	"""
	Persist render_status='failed' and the error message to an EpisodeComposition.
	"""
	try:
		import asyncio
		from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
		from sqlalchemy.orm import sessionmaker
		from sqlalchemy import select
		from src.config import settings
		from src.models.episode_composition import EpisodeComposition

		async def _do_fail() -> None:
			engine = create_async_engine(settings.database_url, echo=False)
			async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

			async with async_session() as session:
				result = await session.execute(
					select(EpisodeComposition).where(
						EpisodeComposition.id == composition_id
					)
				)
				composition = result.scalar_one_or_none()
				if composition:
					composition.render_status = "failed"
					composition.render_error = error
				await session.commit()

			await engine.dispose()

		loop = asyncio.new_event_loop()
		try:
			loop.run_until_complete(_do_fail())
		finally:
			loop.close()

	except Exception as exc:
		logger.error(
			"Failed to mark composition %s as failed: %s", composition_id, exc
		)
