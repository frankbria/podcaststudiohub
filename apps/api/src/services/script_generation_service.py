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
import re
import xml.etree.ElementTree as ET
from typing import Optional, Dict, Any, Tuple
from uuid import UUID
from datetime import datetime
from pathlib import Path

from podcastfy.content_generator import ContentGenerator

from ..config import settings
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
		longform: bool = False,
		max_validation_retries: Optional[int] = None
	) -> GenerationResult:
		"""
		Generate podcast script for an episode.

		Retrieves episode, aggregates extracted content from all completed content sources,
		generates transcript using Gemini via Podcastfy, and stores the result.
		Retries generation up to max_validation_retries times on validation failure.

		Args:
			db: AsyncSession - Database session
			episode_id: UUID of episode to generate script for
			template_config: Optional custom conversation configuration
			longform: Whether to generate long-form content (30+ min)
			max_validation_retries: Maximum retries on validation failure (defaults to settings value)

		Returns:
			GenerationResult with success status and transcript or error

		Raises:
			ValueError: If episode not found or invalid state
		"""
		if max_validation_retries is None:
			max_validation_retries = settings.TRANSCRIPT_VALIDATION_MAX_RETRIES
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

		for retry_attempt in range(1, max_validation_retries + 1):
			try:
				# Generate transcript using Podcastfy
				transcript = await self._call_gemini_api(
					combined_content,
					template_config,
					longform
				)

				# Validate transcript format
				is_valid, error_message = self._validate_transcript(transcript)

				if not is_valid:
					logger.warning(
						f"Transcript validation failed (attempt {retry_attempt}/"
						f"{max_validation_retries}): {error_message}"
					)

					if retry_attempt == max_validation_retries:
						logger.error(
							f"Transcript validation failed after "
							f"{max_validation_retries} attempts for episode {episode_id}: "
							f"{error_message}"
						)
						await self._update_status(
							db, episode, 'failed',
							{
								"stage": "validation",
								"progress": 0,
								"error_message": f"Script generation validation failed: {error_message}"
							}
						)
						return GenerationResult(success=False, error_message=error_message)

					logger.info(
						f"Retrying generation (attempt {retry_attempt + 1}/"
						f"{max_validation_retries}) for episode {episode_id}..."
					)
					continue

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
				# Handle API failures - do not retry on exceptions
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

		# Should never reach here given the loop logic, but guard against it
		return GenerationResult(success=False, error_message="Unexpected generation failure")

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
				parts.append("=== Source: Text Content ===\n")

			# Add extracted content
			parts.append(source.extracted_content)
			parts.append("\n\n")  # Separator

		return "\n".join(parts)

	async def _call_gemini_api(
		self,
		input_content: str,
		template_config: Optional[Dict[str, Any]],
		longform: bool,
		max_retries: Optional[int] = None,
		timeout_seconds: Optional[int] = None
	) -> str:
		"""
		Call Gemini API via Podcastfy to generate transcript with timeout and retry logic.

		Wraps synchronous Podcastfy ContentGenerator with async, adding configurable
		timeout protection and exponential backoff retry logic.

		Args:
			input_content: Combined content to generate from
			template_config: Optional conversation configuration
			longform: Whether to generate long-form content
			max_retries: Maximum retry attempts (defaults to settings.GEMINI_API_MAX_RETRIES)
			timeout_seconds: Timeout in seconds per attempt (defaults to settings.GEMINI_API_TIMEOUT)

		Returns:
			Generated transcript XML string

		Raises:
			TimeoutError: If all retry attempts exceed the timeout
			Exception: If all retry attempts fail with non-timeout errors
		"""
		if max_retries is None:
			max_retries = settings.GEMINI_API_MAX_RETRIES
		if timeout_seconds is None:
			timeout_seconds = settings.GEMINI_API_TIMEOUT

		for attempt in range(1, max_retries + 1):
			try:
				logger.info(
					f"Gemini API call attempt {attempt}/{max_retries} "
					f"(timeout: {timeout_seconds}s)"
				)

				transcript = await asyncio.wait_for(
					asyncio.to_thread(self._call_gemini_sync, input_content, template_config, longform),
					timeout=timeout_seconds
				)

				logger.info(f"Gemini API call succeeded on attempt {attempt}")
				return transcript

			except asyncio.TimeoutError:
				logger.warning(
					f"Gemini API timeout on attempt {attempt}/{max_retries}"
				)

				if attempt == max_retries:
					error_msg = (
						f"Gemini API request exceeded {timeout_seconds} second timeout "
						f"after {max_retries} attempts"
					)
					logger.error(error_msg)
					raise TimeoutError(error_msg)

				backoff_delay = 5 * (2 ** (attempt - 1))
				logger.info(f"Retrying after {backoff_delay}s delay...")
				await asyncio.sleep(backoff_delay)

			except Exception as e:
				logger.error(f"Gemini API error on attempt {attempt}/{max_retries}: {str(e)}")

				if attempt == max_retries:
					raise

				backoff_delay = 5 * (2 ** (attempt - 1))
				logger.info(f"Retrying after {backoff_delay}s delay...")
				await asyncio.sleep(backoff_delay)

		raise RuntimeError("Script generation exhausted all retries")

	def _call_gemini_sync(
		self,
		input_content: str,
		template_config: Optional[Dict[str, Any]],
		longform: bool
	) -> str:
		"""
		Synchronous wrapper for Gemini API call via Podcastfy.

		Args:
			input_content: Combined content to generate from
			template_config: Optional conversation configuration
			longform: Whether to generate long-form content

		Returns:
			Generated transcript XML string
		"""
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

	def _validate_transcript(self, transcript: str) -> Tuple[bool, Optional[str]]:
		"""
		Comprehensive transcript validation.

		Checks XML structure, speaker presence, content length, speaker balance,
		AI artifact detection, and conversational turn count.

		Args:
			transcript: Generated transcript string

		Returns:
			Tuple of (success: bool, error_message: Optional[str]).
			If validation passes, returns (True, None).
			If validation fails, returns (False, descriptive error message).
		"""
		# 1. Validate XML structure
		try:
			ET.fromstring(f"<root>{transcript}</root>")
		except ET.ParseError as e:
			return False, f"Invalid XML structure: {str(e)}"

		# 2. Check for required speaker tags (opening and closing)
		if '<Person1>' not in transcript or '</Person1>' not in transcript:
			return False, "Missing or unclosed Person1 tags"

		if '<Person2>' not in transcript or '</Person2>' not in transcript:
			return False, "Missing or unclosed Person2 tags"

		# 3. Extract speaker contents
		person1_content = self._extract_speaker_content(transcript, 'Person1')
		person2_content = self._extract_speaker_content(transcript, 'Person2')

		# 4. Check for empty dialogue sections
		if not person1_content.strip():
			return False, "Person1 has no dialogue content"

		if not person2_content.strip():
			return False, "Person2 has no dialogue content"

		# 5. Check minimum content length
		combined_words = len((person1_content + ' ' + person2_content).split())
		min_words = settings.MIN_TRANSCRIPT_WORDS

		if combined_words < min_words:
			return False, (
				f"Transcript too short: {combined_words} words "
				f"(minimum: {min_words})"
			)

		# 6. Check speaker balance
		person1_words = len(person1_content.split())
		person2_words = len(person2_content.split())
		total_words = person1_words + person2_words

		if total_words == 0:
			return False, "No dialogue content found"

		person1_percent = (person1_words / total_words) * 100
		person2_percent = (person2_words / total_words) * 100
		balance_threshold = settings.MAX_SPEAKER_IMBALANCE_PERCENT

		if person1_percent > balance_threshold:
			return False, (
				f"Speaker imbalance detected: "
				f"Person1: {person1_percent:.1f}%, Person2: {person2_percent:.1f}%"
			)

		if person2_percent > balance_threshold:
			return False, (
				f"Speaker imbalance detected: "
				f"Person1: {person1_percent:.1f}%, Person2: {person2_percent:.1f}%"
			)

		# 7. Check for AI artifacts
		artifact = self._check_for_ai_artifacts(person1_content + ' ' + person2_content)
		if artifact:
			return False, f"Detected AI artifacts: {artifact}"

		# 8. Validate conversation turn count
		turns = self._count_speaker_turns(transcript)
		min_turns = settings.MIN_CONVERSATION_TURNS

		if turns < min_turns:
			return False, (
				f"Not enough conversational turns: {turns} (minimum: {min_turns})"
			)

		return True, None

	def _extract_speaker_content(self, transcript: str, speaker: str) -> str:
		"""
		Extract all dialogue content for a speaker.

		Args:
			transcript: Full transcript XML string
			speaker: Speaker tag name (e.g. 'Person1')

		Returns:
			Combined string of all content between speaker tags
		"""
		pattern = f'<{speaker}>(.*?)</{speaker}>'
		matches = re.findall(pattern, transcript, re.DOTALL)
		return ' '.join(matches)

	def _check_for_ai_artifacts(self, text: str) -> Optional[str]:
		"""
		Check text for common AI generation artifacts.

		Uses configurable patterns from settings.AI_ARTIFACT_PATTERNS.

		Args:
			text: Combined dialogue text to check

		Returns:
			Name of detected artifact, or None if no artifacts found
		"""
		artifact_patterns = [
			(p.strip(), p.strip().title())
			for p in settings.AI_ARTIFACT_PATTERNS.split(',')
			if p.strip()
		]

		for pattern, artifact_name in artifact_patterns:
			if re.search(re.escape(pattern), text, re.IGNORECASE):
				return artifact_name

		return None

	def _count_speaker_turns(self, transcript: str) -> int:
		"""
		Count total number of speaker turns in transcript.

		Args:
			transcript: Full transcript XML string

		Returns:
			Total number of speaker turns (Person1 + Person2 occurrences)
		"""
		person1_count = len(re.findall(r'<Person1>', transcript))
		person2_count = len(re.findall(r'<Person2>', transcript))
		return person1_count + person2_count

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
