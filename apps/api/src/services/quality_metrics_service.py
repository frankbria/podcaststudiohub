"""
Quality metrics calculator service for podcast transcript analysis.

This service parses XML podcast transcripts to calculate content quality metrics
including length, coherence, tone, speaker balance, and dialogue banter detection.
Metrics are stored in the Episode.generation_progress.quality_metrics JSONB field.

Key Features:
- XML transcript parsing (Person1/Person2 dialogue extraction)
- Length metrics (total words, estimated duration)
- Coherence scoring (sentence variation analysis)
- Tone detection (casual, academic, humorous via keyword matching)
- Speaker balance analysis (word ratio, balanced flag)
- Banter detection (turn-taking, monologue detection)
- JSONB storage in Episode.generation_progress.quality_metrics

Quality Metrics:
- total_words: Combined word count from both speakers
- duration_estimate_minutes: Based on 150 words/minute speaking rate
- coherence_score: 0.0-1.0 scale based on sentence length variation
- tone: "casual" | "academic" | "humorous" (keyword-based detection)
- speaker_balance_ratio: Person1_words / Person2_words
- is_balanced: True if ratio between 0.3-3.33 (30/70 to 70/30 range)
- max_monologue_words: Longest segment without speaker turn
- dialogue_turns: Number of Person1 ↔ Person2 switches
- has_good_banter: True if max_monologue <= 200 words AND turns >= 5
"""

import asyncio
import logging
import xml.etree.ElementTree as ET
from typing import Optional, Dict, Any, List
from pathlib import Path
from dataclasses import dataclass, asdict
import statistics

from sqlalchemy.ext.asyncio import AsyncSession

from .episode_service import get_episode_by_id, update_episode


logger = logging.getLogger(__name__)


# Tone detection keyword sets
TONE_KEYWORDS = {
	"casual": ["yeah", "cool", "awesome", "hey", "stuff", "thing", "kinda", "gonna"],
	"academic": ["furthermore", "hypothesis", "research", "analysis", "demonstrate", "conclude", "evidence"],
	"humorous": ["haha", "lol", "funny", "joke", "hilarious", "kidding", "pun"]
}


@dataclass
class QualityMetrics:
	"""
	Data structure for transcript quality metrics.

	Attributes:
		total_words: Combined word count from both speakers
		duration_estimate_minutes: Estimated podcast duration (150 words/min)
		coherence_score: 0.0-1.0 score based on sentence variation
		tone: Detected tone category ("casual" | "academic" | "humorous")
		speaker_balance_ratio: Person1 words / Person2 words
		is_balanced: True if ratio between 0.3 and 3.33 (30/70 to 70/30)
		max_monologue_words: Longest consecutive segment without speaker change
		dialogue_turns: Number of Person1 ↔ Person2 switches
		has_good_banter: True if max_monologue <= 200 words AND turns >= 5
	"""
	total_words: int
	duration_estimate_minutes: float
	coherence_score: float
	tone: str
	speaker_balance_ratio: float
	is_balanced: bool
	max_monologue_words: int
	dialogue_turns: int
	has_good_banter: bool

	def to_dict(self) -> Dict[str, Any]:
		"""Convert metrics to dictionary for JSONB storage."""
		return asdict(self)


class QualityMetricsCalculator:
	"""
	Calculator for podcast transcript quality metrics.

	Parses XML transcripts with Person1/Person2 dialogue tags and calculates
	comprehensive quality metrics for content assessment and pre-screening.
	"""

	def __init__(self):
		"""Initialize quality metrics calculator."""
		self.logger = logging.getLogger(__name__)

	async def calculate_metrics(
		self,
		episode_id: str,
		transcript_path: Optional[str] = None
	) -> QualityMetrics:
		"""
		Calculate quality metrics from episode transcript XML.

		Args:
			episode_id: Episode UUID for transcript lookup
			transcript_path: Optional explicit transcript path, defaults to data/transcripts/{episode_id}.xml

		Returns:
			QualityMetrics object with all calculated metrics

		Raises:
			FileNotFoundError: If transcript file doesn't exist
			ET.ParseError: If XML is malformed
			ValueError: If transcript has no valid dialogue content
		"""
		# Construct transcript path if not provided
		if transcript_path is None:
			transcript_path = f"data/transcripts/{episode_id}.xml"

		# Read and parse transcript XML
		transcript_content = await self._read_transcript_file(transcript_path)
		person1_segments, person2_segments = self._parse_transcript_xml(transcript_content)

		# Validate we have dialogue content
		if not person1_segments and not person2_segments:
			raise ValueError("Transcript contains no valid Person1 or Person2 dialogue")

		# Calculate all metrics
		total_words = self._calculate_total_words(person1_segments, person2_segments)
		duration_estimate = self._calculate_duration_estimate(total_words)
		coherence_score = self._calculate_coherence_score(person1_segments, person2_segments)
		tone = self._detect_tone(person1_segments, person2_segments)
		speaker_balance_ratio = self._calculate_speaker_balance_ratio(person1_segments, person2_segments)
		is_balanced = self._is_speaker_balance_good(speaker_balance_ratio)
		dialogue_turns = self._count_dialogue_turns(person1_segments, person2_segments)
		max_monologue_words = self._find_max_monologue(person1_segments, person2_segments)
		has_good_banter = self._detect_good_banter(max_monologue_words, dialogue_turns)

		metrics = QualityMetrics(
			total_words=total_words,
			duration_estimate_minutes=duration_estimate,
			coherence_score=coherence_score,
			tone=tone,
			speaker_balance_ratio=speaker_balance_ratio,
			is_balanced=is_balanced,
			max_monologue_words=max_monologue_words,
			dialogue_turns=dialogue_turns,
			has_good_banter=has_good_banter
		)

		self.logger.info(
			f"Calculated quality metrics for episode {episode_id}: "
			f"{total_words} words, {duration_estimate:.1f} min, "
			f"coherence {coherence_score:.2f}, tone {tone}, "
			f"balance {speaker_balance_ratio:.2f}, turns {dialogue_turns}"
		)

		return metrics

	async def calculate_and_store_metrics(
		self,
		db: AsyncSession,
		episode_id: str,
		transcript_path: Optional[str] = None
	) -> QualityMetrics:
		"""
		Calculate quality metrics and store in episode.generation_progress.quality_metrics.

		Args:
			db: Database session
			episode_id: Episode UUID
			transcript_path: Optional explicit transcript path

		Returns:
			QualityMetrics object

		Raises:
			ValueError: If episode not found or transcript invalid
		"""
		# Get episode to verify it exists
		episode = await get_episode_by_id(db, episode_id)
		if not episode:
			raise ValueError(f"Episode {episode_id} not found")

		# Calculate metrics
		metrics = await self.calculate_metrics(episode_id, transcript_path)

		# Update episode.generation_progress with quality metrics
		current_progress = episode.generation_progress or {}
		current_progress["quality_metrics"] = metrics.to_dict()

		# Update episode in database
		await update_episode(db, episode_id, {"generation_progress": current_progress})

		self.logger.info(
			f"Stored quality metrics in episode {episode_id} generation_progress"
		)

		return metrics

	async def _read_transcript_file(self, transcript_path: str) -> str:
		"""
		Read transcript file content asynchronously.

		Args:
			transcript_path: Path to transcript XML file

		Returns:
			File content as string

		Raises:
			FileNotFoundError: If file doesn't exist
		"""
		def _read_file():
			path = Path(transcript_path)
			if not path.exists():
				raise FileNotFoundError(f"Transcript file not found: {transcript_path}")
			return path.read_text(encoding='utf-8')

		return await asyncio.to_thread(_read_file)

	def _parse_transcript_xml(self, xml_content: str) -> tuple[List[str], List[str]]:
		"""
		Parse XML transcript and extract Person1/Person2 dialogue segments.

		Args:
			xml_content: XML string with <Person1> and <Person2> tags

		Returns:
			Tuple of (person1_segments, person2_segments) as lists of strings

		Raises:
			ET.ParseError: If XML is malformed
		"""
		# Wrap content in root tag if not already wrapped
		if not xml_content.strip().startswith('<root>'):
			xml_content = f'<root>{xml_content}</root>'

		root = ET.fromstring(xml_content)

		# Extract all Person1 and Person2 segments
		person1_segments = [elem.text.strip() for elem in root.findall('.//Person1') if elem.text and elem.text.strip()]
		person2_segments = [elem.text.strip() for elem in root.findall('.//Person2') if elem.text and elem.text.strip()]

		return person1_segments, person2_segments

	def _calculate_total_words(self, person1_segments: List[str], person2_segments: List[str]) -> int:
		"""
		Calculate total word count from both speakers.

		Args:
			person1_segments: List of Person1 dialogue strings
			person2_segments: List of Person2 dialogue strings

		Returns:
			Total word count
		"""
		person1_words = sum(len(segment.split()) for segment in person1_segments)
		person2_words = sum(len(segment.split()) for segment in person2_segments)
		return person1_words + person2_words

	def _calculate_duration_estimate(self, total_words: int) -> float:
		"""
		Estimate podcast duration based on speaking rate.

		Args:
			total_words: Total word count

		Returns:
			Duration in minutes (assumes 150 words/minute speaking rate)
		"""
		return total_words / 150.0

	def _calculate_coherence_score(self, person1_segments: List[str], person2_segments: List[str]) -> float:
		"""
		Calculate coherence score based on sentence length variation.

		Higher variation indicates more dynamic dialogue. Score normalized to 0.0-1.0.

		Args:
			person1_segments: List of Person1 dialogue strings
			person2_segments: List of Person2 dialogue strings

		Returns:
			Coherence score between 0.0 (monotone) and 1.0 (varied)
		"""
		all_segments = person1_segments + person2_segments

		if len(all_segments) < 2:
			# Need at least 2 segments to calculate variation
			return 0.5

		# Count words in each segment
		segment_lengths = [len(segment.split()) for segment in all_segments]

		# Calculate standard deviation of segment lengths
		mean_length = statistics.mean(segment_lengths)

		if mean_length == 0:
			return 0.2

		try:
			std_dev = statistics.stdev(segment_lengths)
		except statistics.StatisticsError:
			# All values are the same
			return 0.2

		# Normalize: higher variation = better coherence
		# Formula: min(1.0, std_dev / mean_length * 0.5 + 0.5)
		coherence = min(1.0, std_dev / mean_length * 0.5 + 0.5)

		return round(coherence, 2)

	def _detect_tone(self, person1_segments: List[str], person2_segments: List[str]) -> str:
		"""
		Detect dominant tone using keyword matching.

		Args:
			person1_segments: List of Person1 dialogue strings
			person2_segments: List of Person2 dialogue strings

		Returns:
			Tone category: "casual" | "academic" | "humorous"
		"""
		all_text = " ".join(person1_segments + person2_segments).lower()

		# Count keyword matches for each tone
		tone_counts = {}
		for tone, keywords in TONE_KEYWORDS.items():
			count = sum(all_text.count(keyword) for keyword in keywords)
			tone_counts[tone] = count

		# Return tone with highest count, default to casual on tie
		if tone_counts["casual"] >= tone_counts["academic"] and tone_counts["casual"] >= tone_counts["humorous"]:
			return "casual"
		elif tone_counts["academic"] >= tone_counts["humorous"]:
			return "academic"
		else:
			return "humorous"

	def _calculate_speaker_balance_ratio(self, person1_segments: List[str], person2_segments: List[str]) -> float:
		"""
		Calculate speaker balance ratio (Person1 words / Person2 words).

		Args:
			person1_segments: List of Person1 dialogue strings
			person2_segments: List of Person2 dialogue strings

		Returns:
			Balance ratio, or float('inf') if Person2 has zero words
		"""
		person1_words = sum(len(segment.split()) for segment in person1_segments)
		person2_words = sum(len(segment.split()) for segment in person2_segments)

		if person2_words == 0:
			return float('inf')

		ratio = person1_words / person2_words
		return round(ratio, 2)

	def _is_speaker_balance_good(self, ratio: float) -> bool:
		"""
		Check if speaker balance ratio is within acceptable range (30/70 to 70/30).

		Args:
			ratio: Speaker balance ratio (Person1 / Person2)

		Returns:
			True if ratio between 0.3 and 3.33 (equivalent to 30/70 - 70/30)
		"""
		return 0.3 <= ratio <= 3.33

	def _count_dialogue_turns(self, person1_segments: List[str], person2_segments: List[str]) -> int:
		"""
		Count number of speaker turn changes (Person1 ↔ Person2 switches).

		Reconstructs dialogue order by interleaving segments and counts transitions.
		Assumes segments alternate between speakers (Person1, Person2, Person1, ...).

		Args:
			person1_segments: List of Person1 dialogue strings
			person2_segments: List of Person2 dialogue strings

		Returns:
			Number of speaker switches
		"""
		# Reconstruct dialogue order (assumes alternating pattern)
		max_segments = max(len(person1_segments), len(person2_segments))
		dialogue_order = []

		for i in range(max_segments):
			if i < len(person1_segments):
				dialogue_order.append(('Person1', person1_segments[i]))
			if i < len(person2_segments):
				dialogue_order.append(('Person2', person2_segments[i]))

		# Count transitions
		turns = 0
		for i in range(1, len(dialogue_order)):
			if dialogue_order[i][0] != dialogue_order[i-1][0]:
				turns += 1

		return turns

	def _find_max_monologue(self, person1_segments: List[str], person2_segments: List[str]) -> int:
		"""
		Find longest consecutive segment word count without speaker change.

		Args:
			person1_segments: List of Person1 dialogue strings
			person2_segments: List of Person2 dialogue strings

		Returns:
			Maximum monologue word count
		"""
		# Reconstruct dialogue order (assumes alternating pattern)
		max_segments = max(len(person1_segments), len(person2_segments))
		dialogue_order = []

		for i in range(max_segments):
			if i < len(person1_segments):
				dialogue_order.append(('Person1', person1_segments[i]))
			if i < len(person2_segments):
				dialogue_order.append(('Person2', person2_segments[i]))

		if not dialogue_order:
			return 0

		# Track consecutive words for same speaker
		max_monologue = 0
		current_speaker = dialogue_order[0][0]
		current_words = len(dialogue_order[0][1].split())

		for i in range(1, len(dialogue_order)):
			speaker, text = dialogue_order[i]
			words = len(text.split())

			if speaker == current_speaker:
				# Same speaker continues
				current_words += words
			else:
				# Speaker changed
				max_monologue = max(max_monologue, current_words)
				current_speaker = speaker
				current_words = words

		# Check final monologue
		max_monologue = max(max_monologue, current_words)

		return max_monologue

	def _detect_good_banter(self, max_monologue_words: int, dialogue_turns: int) -> bool:
		"""
		Detect if transcript has good banter (dynamic turn-taking, no long monologues).

		Args:
			max_monologue_words: Longest consecutive segment without speaker change
			dialogue_turns: Number of speaker switches

		Returns:
			True if max_monologue <= 200 words AND dialogue_turns >= 5
		"""
		return max_monologue_words <= 200 and dialogue_turns >= 5
