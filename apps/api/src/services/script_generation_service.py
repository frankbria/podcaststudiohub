"""
Script generation service for generating podcast transcripts using Gemini.

This service wraps Podcastfy content_generator module to generate podcast transcripts
from extracted content sources. It integrates with the Episode model for status tracking
and stores generated transcripts as files.

Key Features:
- Multi-source content aggregation from ContentSource extracted_content
- Gemini API integration via Podcastfy ContentGenerator
- Episode status management (draft → queued → generating → complete/failed)
- Transcript file storage with transcript_path updates
- generation_progress JSONB tracking
- Template configuration support

Status Flow:
- draft → queued (when generation starts)
- queued → generating (during Gemini API call)
- generating → complete (on successful generation)
- generating → failed (on API failure, validation error)
"""

import asyncio
import logging
import os
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime
from pathlib import Path

from podcastfy.content_generator import ContentGenerator

from ..models import Episode
from ..schemas.episode import EpisodeUpdate
from .episode_service import get_episode_by_id, update_episode, update_generation_status
from .content_service import get_content_sources


logger = logging.getLogger(__name__)


class GenerationResult:
	"""
	Data structure for script generation results.

	Attributes:
		success: Whether generation succeeded
		transcript: Generated transcript XML content (None if failed)
		transcript_path: File path where transcript was saved (None if failed)
		error_message: Error details (None if succeeded)
		word_count: Number of words in generated transcript
	"""
	def __init__(
		self,
		success: bool,
		transcript: Optional[str] = None,
		transcript_path: Optional[str] = None,
		error_message: Optional[str] = None
	):
		self.success = success
		self.transcript = transcript
		self.transcript_path = transcript_path
		self.error_message = error_message
		self.word_count = len(transcript.split()) if transcript else 0


class ScriptGenerationService:
	"""
	Service for generating podcast scripts using Gemini via Podcastfy.

	Wraps Podcastfy's synchronous ContentGenerator with async interfaces
	and integrates with the Episode model for status tracking and transcript storage.
	"""

	def __init__(self):
		"""Initialize the script generation service."""
		# ContentGenerator will be initialized per-request to allow custom configs
		pass

	async def generate_script(
		self,
		db,
		episode_id: UUID,
		template_config: Optional[Dict[str, Any]] = None,
		longform: bool = False
	) -> GenerationResult:
		"""
		Generate podcast script for an episode.

		Retrieves episode, aggregates extracted content from all completed content sources,
		generates transcript using Gemini via Podcastfy, and stores the result.

		Args:
			db: AsyncSession - Database session
			episode_id: UUID of episode to generate script for
			template_config: Optional custom conversation configuration
			longform: Whether to generate long-form content (30+ min)

		Returns:
			GenerationResult with success status and transcript or error

		Raises:
			ValueError: If episode not found or invalid state
		"""
		# Retrieve episode
		episode = await get_episode_by_id(db, episode_id)
		if not episode:
			raise ValueError(f"Episode {episode_id} not found")

		# Validate episode is in valid state for generation
		if episode.generation_status not in ['draft', 'queued']:
			raise ValueError(
				f"Episode {episode_id} status is '{episode.generation_status}', "
				"expected 'draft' or 'queued'"
			)

		# Update status to 'queued' if currently 'draft'
		if episode.generation_status == 'draft':
			await self._update_status(
				db, episode, 'queued',
				{"stage": "queued", "progress": 0, "started_at": datetime.utcnow().isoformat()}
			)

		# Retrieve content sources with extraction_status='complete'
		all_content_sources, _ = await get_content_sources(db, episode_id)
		completed_sources = [
			source for source in all_content_sources
			if source.extraction_status == 'complete'
		]

		if not completed_sources:
			error_msg = f"No completed content sources for episode {episode_id}"
			logger.error(error_msg)
			await self._update_status(
				db, episode, 'failed',
				{"stage": "generating", "progress": 0, "error_message": error_msg}
			)
			return GenerationResult(success=False, error_message=error_msg)

		# Validate all sources have non-empty extracted_content
		has_content = any(
			source.extracted_content and source.extracted_content.strip()
			for source in completed_sources
		)
		if not has_content:
			error_msg = "Combined content is empty after extraction"
			logger.error(error_msg)
			await self._update_status(
				db, episode, 'failed',
				{"stage": "generating", "progress": 0, "error_message": error_msg}
			)
			return GenerationResult(success=False, error_message=error_msg)

		# Concatenate extracted content from all sources
		combined_content = self._concatenate_content(completed_sources)

		logger.info(
			f"Generating script for episode {episode_id} from {len(completed_sources)} "
			f"sources ({len(combined_content)} characters)"
		)

		# Update status to 'generating' before API call
		await self._update_status(
			db, episode, 'generating',
			{"stage": "generating", "progress": 50}
		)

		try:
			# Generate transcript using Podcastfy
			transcript = await self._call_gemini_api(
				combined_content,
				template_config,
				longform
			)

			# Validate transcript format
			if not self._validate_transcript(transcript):
				error_msg = "Generated transcript missing Person1/Person2 tags"
				logger.error(f"Invalid transcript format for episode {episode_id}")
				await self._update_status(
					db, episode, 'failed',
					{"stage": "generating", "progress": 0, "error_message": error_msg}
				)
				return GenerationResult(success=False, error_message=error_msg)

			# Save transcript to file
			transcript_path = await self._save_transcript(episode_id, transcript)

			# Update episode with transcript_path and status='complete'
			update_data = EpisodeUpdate(transcript_path=transcript_path)
			await update_episode(db, episode, update_data)

			await self._update_status(
				db, episode, 'complete',
				{
					"stage": "complete",
					"progress": 100,
					"completed_at": datetime.utcnow().isoformat()
				}
			)

			logger.info(
				f"Successfully generated script for episode {episode_id}, "
				f"saved to {transcript_path}"
			)
			return GenerationResult(
				success=True,
				transcript=transcript,
				transcript_path=transcript_path
			)

		except Exception as e:
			# Handle API failures
			error_msg = f"Gemini API error: {str(e)}"
			logger.exception(f"Error generating script for episode {episode_id}: {error_msg}")
			await self._update_status(
				db, episode, 'failed',
				{
					"stage": "generating",
					"progress": 0,
					"error_message": error_msg
				}
			)
			return GenerationResult(success=False, error_message=error_msg)

	# ========================================================================
	# HELPER METHODS
	# ========================================================================

	async def _update_status(
		self,
		db,
		episode: Episode,
		status: str,
		progress_data: Dict[str, Any]
	) -> None:
		"""Update episode generation status and progress."""
		await update_generation_status(db, episode, status, progress_data)

	def _concatenate_content(self, content_sources: list) -> str:
		"""
		Concatenate extracted content from multiple content sources.

		Adds source metadata and separators for clarity.

		Args:
			content_sources: List of ContentSource instances with extracted_content

		Returns:
			Combined content string
		"""
		parts = []
		for source in content_sources:
			source_type = source.source_type
			source_data = source.source_data

			# Add source metadata header
			if source_type == 'url':
				title = source_data.get('title', 'Unknown')
				url = source_data.get('url', '')
				parts.append(f"=== Source: {title} ({url}) ===\n")
			elif source_type == 'pdf':
				filename = source_data.get('filename', 'Unknown')
				parts.append(f"=== Source: PDF - {filename} ===\n")
			elif source_type == 'text':
				parts.append(f"=== Source: Text Content ===\n")

			# Add extracted content
			parts.append(source.extracted_content)
			parts.append("\n\n")  # Separator

		return "\n".join(parts)

	async def _call_gemini_api(
		self,
		input_content: str,
		template_config: Optional[Dict[str, Any]],
		longform: bool
	) -> str:
		"""
		Call Gemini API via Podcastfy to generate transcript.

		Wraps synchronous Podcastfy ContentGenerator with async.

		Args:
			input_content: Combined content to generate from
			template_config: Optional conversation configuration
			longform: Whether to generate long-form content

		Returns:
			Generated transcript XML string

		Raises:
			Exception: If Gemini API call fails
		"""
		# Initialize ContentGenerator with config
		# NOTE: Podcastfy's ContentGenerator is synchronous
		def _generate():
			generator = ContentGenerator(
				is_local=False,
				model_name=os.getenv("GEMINI_MODEL_NAME", "gemini-1.5-pro-latest"),
				api_key_label="GEMINI_API_KEY",
				conversation_config=template_config
			)
			return generator.generate_qa_content(
				input_texts=input_content,
				longform=longform
			)

		# Wrap in async thread
		transcript = await asyncio.to_thread(_generate)
		return transcript

	def _validate_transcript(self, transcript: str) -> bool:
		"""
		Validate transcript format.

		Checks for presence of Person1 and Person2 XML tags.

		Args:
			transcript: Generated transcript string

		Returns:
			True if valid, False otherwise
		"""
		return '<Person1>' in transcript and '<Person2>' in transcript

	async def _save_transcript(self, episode_id: UUID, transcript: str) -> str:
		"""
		Save transcript to file.

		Creates data/transcripts/ directory if not exists.
		Saves transcript as XML file with episode_id as filename.

		Args:
			episode_id: Episode UUID
			transcript: Transcript content to save

		Returns:
			File path where transcript was saved

		Raises:
			IOError: If file cannot be written
		"""
		# Create directory if not exists
		transcripts_dir = Path("data/transcripts")
		transcripts_dir.mkdir(parents=True, exist_ok=True)

		# Save transcript
		transcript_path = transcripts_dir / f"{episode_id}.xml"

		def _write_file():
			with open(transcript_path, 'w', encoding='utf-8') as f:
				f.write(transcript)

		await asyncio.to_thread(_write_file)

		return str(transcript_path)
