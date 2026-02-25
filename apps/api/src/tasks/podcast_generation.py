"""
Celery tasks for podcast generation
Wraps the existing podcastfy CLI functionality
"""
from celery import Task
from typing import Optional, List, Dict, Any
import logging
from datetime import datetime, timezone

from src.worker import celery_app
from src.database import SessionLocal
from src.models.episode import Episode

logger = logging.getLogger(__name__)


def on_generation_success(result: Dict[str, Any], task_id: str, args: list, kwargs: dict) -> None:
	"""
	Persist podcast generation results to the Episode model on task success.

	This callback runs automatically in the Celery worker process after
	generate_podcast_task completes successfully. It updates the Episode
	record with the generated audio file path and metadata.

	Args:
		result: Task return value containing audio_file_path, duration_seconds, etc.
		task_id: Celery task UUID
		args: Positional arguments the task was called with
		kwargs: Keyword arguments the task was called with (must contain episode_id)
	"""
	episode_id = kwargs.get("episode_id")
	if not episode_id:
		logger.warning(
			"on_generation_success called without episode_id in kwargs "
			"(task_id=%s) — skipping DB update",
			task_id,
		)
		return

	if not result or result.get("status") != "success":
		logger.info(
			"Task %s for episode %s did not succeed (status=%s) — skipping DB update",
			task_id,
			episode_id,
			result.get("status") if result else None,
		)
		return

	try:
		with SessionLocal() as db:
			episode = db.query(Episode).filter(Episode.id == episode_id).first()

			if episode is None:
				logger.warning(
					"Episode %s not found in DB during on_generation_success "
					"(task_id=%s) — skipping update",
					episode_id,
					task_id,
				)
				return

			logger.info(
				"Persisting generation results for episode %s (task_id=%s)",
				episode_id,
				task_id,
			)

			episode.file_path = result["audio_file_path"]
			episode.transcript_path = result["transcript_path"]
			episode.duration_seconds = result["duration_seconds"]
			episode.file_size_bytes = result["file_size_bytes"]
			episode.generation_status = "complete"
			episode.generation_progress = {
				"stage": "complete",
				"progress": 100,
				"completed_at": datetime.now(timezone.utc).isoformat(),
			}

			db.commit()
			logger.info("Episode %s updated successfully with generation results", episode_id)

	except Exception:
		logger.exception(
			"Failed to persist generation results for episode %s (task_id=%s)",
			episode_id,
			task_id,
		)


class PodcastGenerationTask(Task):
	"""
	Custom Celery Task class that registers on_generation_success as the
	on_success callback.  Using a base class ensures the callback is
	invoked correctly by the Celery worker without coupling it to the
	task function body.
	"""

	def on_success(self, retval, task_id, args, kwargs):
		"""Delegate to the standalone callback function for easy unit testing."""
		on_generation_success(retval, task_id, args, kwargs)


@celery_app.task(
	bind=True,
	name="generate_podcast",
	time_limit=600,
	base=PodcastGenerationTask,
)
def generate_podcast_task(
	self: Task,
	episode_id: str,
	urls: Optional[List[str]] = None,
	text: Optional[str] = None,
	pdf_paths: Optional[List[str]] = None,
	image_paths: Optional[List[str]] = None,
	youtube_urls: Optional[List[str]] = None,
	topic: Optional[str] = None,
	tts_model: str = "openai",
	conversation_config: Optional[Dict[str, Any]] = None,
	longform: bool = False
) -> Dict[str, Any]:
	"""
	Generate a podcast episode using the existing Podcastfy CLI.

	This task wraps the existing generate_podcast() function from the CLI
	and provides progress tracking for the GUI.

	Args:
		self: Celery task instance (for progress updates)
		episode_id: UUID of the episode being generated
		urls: List of URLs to extract content from
		text: Raw text content
		pdf_paths: List of PDF file paths
		image_paths: List of image file paths
		youtube_urls: List of YouTube URLs
		topic: Topic for content generation (uses web search)
		tts_model: TTS provider (openai, elevenlabs, gemini, etc.)
		conversation_config: Custom conversation configuration
		longform: Whether to generate long-form content

	Returns:
		Dictionary with generation results:
		{
			"status": "success" | "failed",
			"audio_file_path": str,
			"transcript_path": str,
			"duration_seconds": float,
			"file_size_bytes": int,
			"error": Optional[str]
		}
	"""
	try:
		# Stage 1: Content Extraction (0-33%)
		self.update_state(
			state='PROGRESS',
			meta={
				'episode_id': episode_id,
				'stage': 'extraction',
				'progress': 0,
				'status': 'Extracting content from sources...'
			}
		)

		# Import the existing CLI function
		# Note: This imports from the existing podcastfy package
		import sys
		import os
		# Add the root directory to path to import podcastfy
		sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../../..'))

		from podcastfy.client import generate_podcast

		# Update progress after extraction
		self.update_state(
			state='PROGRESS',
			meta={
				'episode_id': episode_id,
				'stage': 'extraction',
				'progress': 33,
				'status': 'Content extracted successfully'
			}
		)

		# Stage 2: Transcript Generation (33-66%)
		self.update_state(
			state='PROGRESS',
			meta={
				'episode_id': episode_id,
				'stage': 'transcript',
				'progress': 33,
				'status': 'Generating podcast transcript...'
			}
		)

		# Generate the podcast using existing CLI
		result = generate_podcast(
			urls=urls,
			text=text,
			file=pdf_paths,
			image_paths=image_paths,
			youtube_urls=youtube_urls,
			topic=topic,
			tts_model=tts_model,
			conversation_config=conversation_config,
			longform=longform,
		)

		self.update_state(
			state='PROGRESS',
			meta={
				'episode_id': episode_id,
				'stage': 'transcript',
				'progress': 66,
				'status': 'Transcript generated successfully'
			}
		)

		# Stage 3: Audio Synthesis (66-100%)
		self.update_state(
			state='PROGRESS',
			meta={
				'episode_id': episode_id,
				'stage': 'audio',
				'progress': 66,
				'status': 'Synthesizing audio...'
			}
		)

		# Extract file information
		import os
		from pydub import AudioSegment

		audio_file_path = result
		file_size_bytes = os.path.getsize(audio_file_path)

		# Get audio duration
		audio = AudioSegment.from_file(audio_file_path)
		duration_seconds = len(audio) / 1000.0

		# Completion
		self.update_state(
			state='PROGRESS',
			meta={
				'episode_id': episode_id,
				'stage': 'complete',
				'progress': 100,
				'status': 'Podcast generated successfully'
			}
		)

		return {
			"status": "success",
			"audio_file_path": audio_file_path,
			"transcript_path": audio_file_path.replace('.mp3', '_transcript.txt'),
			"duration_seconds": duration_seconds,
			"file_size_bytes": file_size_bytes,
			"error": None
		}

	except Exception as e:
		logger.error(f"Podcast generation failed for episode {episode_id}: {str(e)}")
		self.update_state(
			state='FAILURE',
			meta={
				'episode_id': episode_id,
				'stage': 'failed',
				'progress': 0,
				'status': f'Generation failed: {str(e)}'
			}
		)
		return {
			"status": "failed",
			"audio_file_path": None,
			"transcript_path": None,
			"duration_seconds": 0,
			"file_size_bytes": 0,
			"error": str(e)
		}
