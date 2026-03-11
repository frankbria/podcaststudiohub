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


def _download_snippet_from_s3(s3_key: str, dest_dir: str) -> Optional[str]:
	"""
	Download an audio snippet from S3 to a temp directory.

	Args:
		s3_key: S3 object key
		dest_dir: Directory to download to

	Returns:
		Local file path, or None if S3 not configured
	"""
	try:
		from src.config import settings
		from src.services.storage_service import StorageService

		bucket = getattr(settings, "AWS_S3_BUCKET", None)
		if not bucket:
			return None

		local_path = os.path.join(dest_dir, f"snippet_{os.path.basename(s3_key)}")
		storage = StorageService(bucket_name=bucket, region_name=settings.AWS_REGION)

		import asyncio
		loop = asyncio.new_event_loop()
		try:
			loop.run_until_complete(storage.download_file(s3_key, local_path))
		finally:
			loop.close()

		return local_path
	except Exception as e:
		logger.warning(f"Failed to download snippet from S3 ({s3_key}): {e}")
		return None


def _apply_volume(audio: Any, volume_level: float) -> Any:
	"""
	Apply volume scaling to an audio segment.

	Args:
		audio: pydub AudioSegment
		volume_level: Volume multiplier (1.0 = unchanged)

	Returns:
		Adjusted AudioSegment
	"""
	import math
	if volume_level <= 0:
		return audio.apply_gain(-120)  # silence
	if volume_level == 1.0:
		return audio
	gain_db = 20 * math.log10(volume_level)
	return audio.apply_gain(gain_db)


@celery_app.task(bind=True, name="merge_audio_snippets", time_limit=600)
def merge_audio_snippets_task(
	self: Task,
	episode_id: str,
	timeline: List[Dict[str, Any]],
	output_path: str,
	composition_id: Optional[str] = None,
) -> Dict[str, Any]:
	"""
	Merge audio snippets according to the composition timeline.

	Enhanced version that:
	- Downloads snippets from S3 when available
	- Supports per-segment volume, fade in/out, and normalization
	- Handles timeline gaps with silence
	- Updates EpisodeComposition render_status on completion
	- Uploads composed audio to S3

	Args:
		self: Celery task instance
		episode_id: UUID of the episode
		timeline: List of timeline segments with snippet info and positions
		output_path: Path for the final composed audio file
		composition_id: Optional UUID of EpisodeComposition to update

	Returns:
		Dictionary with composition results including output_path and duration
	"""
	try:
		self.update_state(
			state='PROGRESS',
			meta={
				'episode_id': episode_id,
				'progress': 0,
				'status': 'Starting audio composition...'
			}
		)

		from pydub import AudioSegment

		# Sort timeline by position
		sorted_timeline = sorted(
			timeline,
			key=lambda s: float(s.get('position_seconds', 0))
		)

		total_segments = len(sorted_timeline)
		temp_dir = tempfile.mkdtemp(prefix="composition_")
		downloaded_files: List[str] = []
		segment_audios: List[Dict[str, Any]] = []

		try:
			# Phase 1: Download all snippets from S3 or use local paths
			self.update_state(
				state='PROGRESS',
				meta={
					'episode_id': episode_id,
					'progress': 5,
					'status': 'Fetching audio files...'
				}
			)

			for idx, segment in enumerate(sorted_timeline):
				audio_path = None

				# Try S3 key first (preferred for production)
				s3_key = segment.get('s3_key')
				if s3_key:
					audio_path = _download_snippet_from_s3(s3_key, temp_dir)

				# Fall back to local file_path
				if audio_path is None:
					local_path = segment.get('file_path')
					if local_path and os.path.exists(local_path):
						audio_path = local_path

				if audio_path:
					downloaded_files.append(audio_path)

				segment_audios.append({
					'segment': segment,
					'audio_path': audio_path,
				})

			# Phase 2: Build composition
			final_audio = AudioSegment.silent(duration=0)
			current_pos_ms = 0

			for idx, item in enumerate(segment_audios):
				progress = int(10 + (idx / total_segments) * 80)
				segment = item['segment']
				audio_path = item['audio_path']

				self.update_state(
					state='PROGRESS',
					meta={
						'episode_id': episode_id,
						'progress': progress,
						'status': f'Merging segment {idx + 1}/{total_segments}...'
					}
				)

				if audio_path is None:
					logger.warning(
						f"No audio file for segment {idx} in episode {episode_id}, skipping"
					)
					continue

				# Load audio segment
				audio = AudioSegment.from_file(audio_path)

				# Apply normalization
				if segment.get('normalize', False):
					audio = audio.normalize()

				# Apply volume scaling
				volume_level = float(segment.get('volume_level', 1.0))
				if volume_level != 1.0:
					audio = _apply_volume(audio, volume_level)

				# Apply fade in/out
				fade_in_ms = int(segment.get('fade_in_ms', 0))
				fade_out_ms = int(segment.get('fade_out_ms', 0))
				if fade_in_ms > 0:
					audio = audio.fade_in(fade_in_ms)
				if fade_out_ms > 0:
					audio = audio.fade_out(fade_out_ms)

				# Calculate position and add silence gap if needed
				position_ms = int(float(segment.get('position_seconds', 0)) * 1000)
				if position_ms > current_pos_ms:
					silence_duration = position_ms - current_pos_ms
					final_audio += AudioSegment.silent(duration=silence_duration)
					current_pos_ms = position_ms

				# Append audio segment
				final_audio += audio
				current_pos_ms += len(audio)

		finally:
			# Clean up downloaded temp files (not local file_paths passed in)
			for f in downloaded_files:
				if f and f.startswith(temp_dir) and os.path.exists(f):
					try:
						os.unlink(f)
					except Exception:
						pass
			try:
				os.rmdir(temp_dir)
			except Exception:
				pass

		# Phase 3: Export composition
		self.update_state(
			state='PROGRESS',
			meta={
				'episode_id': episode_id,
				'progress': 90,
				'status': 'Exporting composed audio...'
			}
		)

		os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
		final_audio.export(output_path, format="mp3", bitrate="192k")

		file_size_bytes = os.path.getsize(output_path)
		duration_seconds = len(final_audio) / 1000.0

		# Phase 4: Upload to S3 and update composition record
		s3_url = None
		s3_key = None
		try:
			from src.config import settings
			from src.services.storage_service import StorageService
			import asyncio

			bucket = getattr(settings, "AWS_S3_BUCKET", None)
			if bucket and composition_id:
				s3_key = f"compositions/{episode_id}/{composition_id}.mp3"
				storage = StorageService(
					bucket_name=bucket, region_name=settings.AWS_REGION
				)
				loop = asyncio.new_event_loop()
				try:
					s3_url = loop.run_until_complete(
						storage.upload_file(
							file_path=output_path,
							s3_key=s3_key,
							content_type="audio/mpeg",
							public=True,
						)
					)
				finally:
					loop.close()
		except Exception as e:
			logger.warning(f"Failed to upload composition to S3: {e}")

		# Phase 5: Update EpisodeComposition record
		if composition_id:
			try:
				_update_composition_record(
					composition_id=composition_id,
					render_status="complete",
					composed_s3_key=s3_key,
					composed_s3_url=s3_url,
					composed_duration_seconds=duration_seconds,
				)
			except Exception as e:
				logger.warning(f"Failed to update composition record {composition_id}: {e}")

		self.update_state(
			state='PROGRESS',
			meta={
				'episode_id': episode_id,
				'progress': 100,
				'status': 'Composition complete'
			}
		)

		return {
			"status": "success",
			"output_path": output_path,
			"s3_key": s3_key,
			"s3_url": s3_url,
			"duration_seconds": duration_seconds,
			"file_size_bytes": file_size_bytes,
			"error": None
		}

	except Exception as e:
		logger.error(f"Audio composition failed for episode {episode_id}: {str(e)}")

		if composition_id:
			try:
				_update_composition_record(
					composition_id=composition_id,
					render_status="failed",
					render_error=str(e),
				)
			except Exception:
				pass

		return {
			"status": "failed",
			"output_path": None,
			"s3_key": None,
			"s3_url": None,
			"duration_seconds": 0,
			"file_size_bytes": 0,
			"error": str(e)
		}


def _update_composition_record(
	composition_id: str,
	render_status: str,
	render_error: Optional[str] = None,
	composed_s3_key: Optional[str] = None,
	composed_s3_url: Optional[str] = None,
	composed_duration_seconds: Optional[float] = None,
) -> None:
	"""
	Update EpisodeComposition render status in the database synchronously.

	Uses the sync session factory designed for Celery tasks.

	Args:
		composition_id: UUID of the composition record
		render_status: New render status (complete, failed)
		render_error: Error message if failed
		composed_s3_key: S3 key of composed file
		composed_s3_url: Public S3 URL of composed file
		composed_duration_seconds: Duration of composed audio
	"""
	from datetime import datetime
	from sqlalchemy import update
	from uuid import UUID

	from src.database import SyncSessionLocal
	from src.models.episode_composition import EpisodeComposition

	values: Dict[str, Any] = {
		"render_status": render_status,
		"render_error": render_error,
		"last_rendered_at": datetime.utcnow(),
	}
	if composed_s3_key is not None:
		values["composed_s3_key"] = composed_s3_key
	if composed_s3_url is not None:
		values["composed_s3_url"] = composed_s3_url
	if composed_duration_seconds is not None:
		values["composed_duration_seconds"] = composed_duration_seconds

	with SyncSessionLocal() as session:
		session.execute(
			update(EpisodeComposition)
			.where(EpisodeComposition.id == UUID(composition_id))
			.values(**values)
		)
		session.commit()
