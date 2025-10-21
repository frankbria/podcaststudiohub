"""
Celery tasks for podcast generation
Wraps the existing podcastfy CLI functionality
"""
from celery import Task
from typing import Optional, List, Dict, Any
import logging

from src.worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="generate_podcast", time_limit=600)
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
