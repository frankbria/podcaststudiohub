"""
Comprehensive test suite for quality metrics calculator service.

Tests cover:
- XML parsing with valid transcripts, malformed XML, empty tags
- Length metrics (total_words, duration_estimate with known transcripts)
- Coherence score calculation, normalization to 0.0-1.0 range
- Tone detection (casual, academic, humorous, ties)
- Speaker balance (balanced 50/50, 60/40, imbalanced 80/20, extreme 90/10, division by zero)
- Banter detection (good banter, poor banter, edge cases at 200 words)
- Integration tests (full metric calculation, JSONB storage in generation_progress)
- Error handling (missing transcript file, invalid episode_id, malformed XML)

All file I/O and episode_service functions are mocked to avoid external dependencies.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from uuid import uuid4
import xml.etree.ElementTree as ET

from src.services.quality_metrics_service import (
	QualityMetricsCalculator,
	QualityMetrics
)
from src.models import Episode


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def metrics_calculator():
	"""Create QualityMetricsCalculator instance."""
	return QualityMetricsCalculator()


@pytest.fixture
def mock_db():
	"""Create mock database session."""
	return AsyncMock()


@pytest.fixture
def sample_episode():
	"""Create sample episode with generation_progress."""
	return Episode(
		id=uuid4(),
		project_id=uuid4(),
		user_id=uuid4(),
		tenant_id=uuid4(),
		episode_number=1,
		episode_metadata={"title": "Test Episode"},
		generation_status='complete',
		generation_progress={
			"stage": "complete",
			"progress": 100,
			"completed_at": "2024-01-15T10:30:00"
		},
		transcript_path="data/transcripts/test-episode.xml"
	)


@pytest.fixture
def balanced_transcript():
	"""
	Balanced transcript with good banter (50/50 split, many turns, short exchanges).
	Person1: ~150 words, Person2: ~150 words
	"""
	return """<root>
<Person1>Hey there! Welcome to our podcast about artificial intelligence. Today we're diving into machine learning fundamentals and exploring how neural networks actually work under the hood.</Person1>
<Person2>Thanks for having me! I'm really excited to break down these complex topics into something everyone can understand. Machine learning is fascinating once you get past the jargon.</Person2>
<Person1>Absolutely! So let's start with the basics. What exactly is a neural network, and why do we call it that?</Person1>
<Person2>Great question! Neural networks are inspired by biological neurons in our brains. They consist of interconnected nodes that process information in layers, transforming inputs into meaningful outputs.</Person2>
<Person1>That's a perfect explanation. And these networks learn by adjusting connection weights, right? It's like the network gets smarter over time.</Person1>
<Person2>Exactly! Through a process called backpropagation, the network compares its predictions to actual results and fine-tunes itself. It's really quite elegant.</Person2>
<Person1>I love that. The mathematics behind it is beautiful but also practical. What are some real-world applications people might not expect?</Person1>
<Person2>Oh, there are tons! From medical diagnosis to climate modeling, from language translation to music generation. AI is everywhere now, often working behind the scenes.</Person2>
<Person1>That's incredible. And we're just scratching the surface of what's possible with these technologies.</Person1>
<Person2>Absolutely. The future is going to be amazing as these tools become more accessible and powerful.</Person2>
</root>"""


@pytest.fixture
def imbalanced_transcript():
	"""
	Imbalanced transcript (80/20 split, Person1 dominates).
	Person1: ~400 words, Person2: ~100 words
	"""
	return """<root>
<Person1>Welcome everyone to today's deep dive into quantum computing. This is going to be a comprehensive overview covering everything from quantum bits to quantum supremacy. Let me start by explaining the fundamental differences between classical and quantum computing. In classical computing, we use bits that are either zero or one. But in quantum computing, we use qubits that can exist in a superposition of states. This means a qubit can be zero, one, or both simultaneously until we measure it. This property, along with quantum entanglement, gives quantum computers their incredible power. Now, when we talk about quantum entanglement, we're discussing a phenomenon where two qubits become correlated in such a way that the state of one instantly affects the state of the other, regardless of distance. Einstein famously called this spooky action at a distance. These properties enable quantum computers to solve certain problems exponentially faster than classical computers. For instance, factoring large numbers, which is crucial for cryptography, or simulating molecular interactions for drug discovery. The applications are truly revolutionary and we're only beginning to understand the full potential.</Person1>
<Person2>Wow, that's fascinating! So quantum computers could break current encryption methods?</Person2>
<Person1>Yes, that's a significant concern. Current RSA encryption relies on the difficulty of factoring large numbers, which quantum computers could do efficiently using Shor's algorithm. This has led to the development of post-quantum cryptography, which aims to create encryption methods resistant to quantum attacks. It's an arms race between quantum computing capabilities and cryptographic security. We're also seeing incredible progress in quantum error correction, which is essential because qubits are extremely fragile and prone to decoherence.</Person1>
<Person2>That makes sense. Thanks for explaining!</Person2>
</root>"""


@pytest.fixture
def long_monologue_transcript():
	"""
	Transcript with long monologue (>200 words) - poor banter.
	"""
	return """<root>
<Person1>Hello and welcome.</Person1>
<Person2>Today I want to tell you a very long story about my journey into programming. It all started when I was young and fascinated by computers. I spent countless hours learning different programming languages, from Python to JavaScript to C++. Each language taught me something new about how computers think and process information. I remember my first program was a simple calculator, but it felt like magic when it actually worked. From there, I built increasingly complex projects, learning about algorithms, data structures, design patterns, and software architecture. I studied computer science in college, worked on open source projects, contributed to major frameworks, and eventually landed a job at a tech company. Throughout this journey, I've learned that programming is not just about writing code, it's about solving problems, thinking logically, and continuously learning new technologies. The field evolves so rapidly that you can never stop learning. New frameworks emerge, old ones become obsolete, and best practices constantly change. But that's what makes it exciting! Every day brings new challenges and opportunities to grow. I've worked on mobile apps, web applications, backend services, databases, cloud infrastructure, and everything in between. The breadth of knowledge required is enormous, but that's also what makes it rewarding. You're never bored because there's always something new to explore and master in the world of software development.</Person2>
<Person1>That's quite a journey! Thanks for sharing.</Person1>
</root>"""


@pytest.fixture
def casual_tone_transcript():
	"""Transcript with casual tone keywords."""
	return """<root>
<Person1>Hey, what's up? This is gonna be awesome! We're talking about cool stuff today.</Person1>
<Person2>Yeah, totally! I'm super excited. This thing we're discussing is really neat.</Person2>
<Person1>Kinda crazy how it all works, right? It's pretty cool when you think about it.</Person1>
<Person2>For sure! Hey, let's dive into the details now.</Person2>
</root>"""


@pytest.fixture
def academic_tone_transcript():
	"""Transcript with academic tone keywords."""
	return """<root>
<Person1>This research demonstrates significant findings in the field. Our hypothesis was based on prior evidence.</Person1>
<Person2>Furthermore, the analysis reveals compelling patterns. We can conclude that the methodology was sound.</Person2>
<Person1>Indeed. The evidence supports our initial hypothesis. This research contributes to the broader literature.</Person1>
<Person2>The analysis demonstrates clear correlations. Further research is warranted to investigate these phenomena.</Person2>
</root>"""


@pytest.fixture
def humorous_tone_transcript():
	"""Transcript with humorous tone keywords."""
	return """<root>
<Person1>Haha, that's hilarious! You're totally kidding, right? That joke was amazing!</Person1>
<Person2>Lol, no I'm serious! It's funny when you think about it. Such a great pun!</Person2>
<Person1>You're killing me! That's the funniest thing I've heard all day. Haha!</Person1>
<Person2>I know, right? Comedy gold! This is hilarious.</Person2>
</root>"""


# ============================================================================
# XML PARSING TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_parse_valid_transcript(metrics_calculator, balanced_transcript):
	"""Test XML parsing with valid transcript."""
	person1, person2 = metrics_calculator._parse_transcript_xml(balanced_transcript)

	assert len(person1) == 5  # 5 Person1 segments
	assert len(person2) == 5  # 5 Person2 segments
	assert "Welcome to our podcast" in person1[0]
	assert "Thanks for having me" in person2[0]


@pytest.mark.asyncio
async def test_parse_transcript_with_empty_tags(metrics_calculator):
	"""Test parsing handles empty tags gracefully."""
	xml = """<root>
<Person1>Hello world</Person1>
<Person2></Person2>
<Person1>   </Person1>
<Person2>Response here</Person2>
</root>"""

	person1, person2 = metrics_calculator._parse_transcript_xml(xml)

	# Empty and whitespace-only tags should be filtered out
	assert len(person1) == 1
	assert len(person2) == 1
	assert person1[0] == "Hello world"
	assert person2[0] == "Response here"


@pytest.mark.asyncio
async def test_parse_malformed_xml_raises_error(metrics_calculator):
	"""Test malformed XML raises ParseError."""
	malformed_xml = "<Person1>Unclosed tag"

	with pytest.raises(ET.ParseError):
		metrics_calculator._parse_transcript_xml(malformed_xml)


@pytest.mark.asyncio
async def test_parse_transcript_without_root_wrapper(metrics_calculator):
	"""Test parsing adds root wrapper automatically."""
	xml_without_root = "<Person1>Hello</Person1><Person2>World</Person2>"

	person1, person2 = metrics_calculator._parse_transcript_xml(xml_without_root)

	assert len(person1) == 1
	assert len(person2) == 1
	assert person1[0] == "Hello"
	assert person2[0] == "World"


# ============================================================================
# LENGTH METRICS TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_calculate_total_words(metrics_calculator):
	"""Test total word count calculation."""
	person1 = ["Hello world this is a test", "Another segment here"]  # 6 + 3 = 9 words
	person2 = ["Response from person two", "More words here"]  # 4 + 3 = 7 words

	total = metrics_calculator._calculate_total_words(person1, person2)

	assert total == 16


@pytest.mark.asyncio
async def test_calculate_duration_estimate(metrics_calculator):
	"""Test duration estimate calculation (150 words/min)."""
	# 300 words should be 2 minutes
	duration = metrics_calculator._calculate_duration_estimate(300)
	assert duration == 2.0

	# 450 words should be 3 minutes
	duration = metrics_calculator._calculate_duration_estimate(450)
	assert duration == 3.0

	# 75 words should be 0.5 minutes
	duration = metrics_calculator._calculate_duration_estimate(75)
	assert duration == 0.5


# ============================================================================
# COHERENCE SCORE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_coherence_score_with_varied_segments(metrics_calculator):
	"""Test coherence score with varied segment lengths (high variation)."""
	person1 = ["Short", "This is a much longer segment with many more words"]
	person2 = ["Medium length segment", "Another one"]

	score = metrics_calculator._calculate_coherence_score(person1, person2)

	# High variation should give higher score
	assert 0.0 <= score <= 1.0
	assert score > 0.5  # Should be above baseline


@pytest.mark.asyncio
async def test_coherence_score_with_uniform_segments(metrics_calculator):
	"""Test coherence score with uniform segment lengths (low variation)."""
	person1 = ["This has five words", "This also has five"]
	person2 = ["Five words here too", "And five more here"]

	score = metrics_calculator._calculate_coherence_score(person1, person2)

	# Uniform segments (no variation) should give baseline score
	assert 0.0 <= score <= 1.0
	assert score == 0.5  # Baseline when std_dev = 0


@pytest.mark.asyncio
async def test_coherence_score_with_single_segment(metrics_calculator):
	"""Test coherence score with only one segment returns default."""
	person1 = ["Single segment"]
	person2 = []

	score = metrics_calculator._calculate_coherence_score(person1, person2)

	# Single segment should return baseline
	assert score == 0.5


@pytest.mark.asyncio
async def test_coherence_score_normalized_range(metrics_calculator):
	"""Test coherence score is always in 0.0-1.0 range."""
	# Extreme variation
	person1 = ["a", "a b c d e f g h i j k l m n o p q r s t u v w x y z"]
	person2 = ["a b", "a b c d e"]

	score = metrics_calculator._calculate_coherence_score(person1, person2)

	assert 0.0 <= score <= 1.0


# ============================================================================
# TONE DETECTION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_detect_casual_tone(metrics_calculator, casual_tone_transcript):
	"""Test casual tone detection."""
	person1, person2 = metrics_calculator._parse_transcript_xml(casual_tone_transcript)
	tone = metrics_calculator._detect_tone(person1, person2)

	assert tone == "casual"


@pytest.mark.asyncio
async def test_detect_academic_tone(metrics_calculator, academic_tone_transcript):
	"""Test academic tone detection."""
	person1, person2 = metrics_calculator._parse_transcript_xml(academic_tone_transcript)
	tone = metrics_calculator._detect_tone(person1, person2)

	assert tone == "academic"


@pytest.mark.asyncio
async def test_detect_humorous_tone(metrics_calculator, humorous_tone_transcript):
	"""Test humorous tone detection."""
	person1, person2 = metrics_calculator._parse_transcript_xml(humorous_tone_transcript)
	tone = metrics_calculator._detect_tone(person1, person2)

	assert tone == "humorous"


@pytest.mark.asyncio
async def test_tone_defaults_to_casual_on_tie(metrics_calculator):
	"""Test tone defaults to casual when no keywords match."""
	person1 = ["This is neutral content without any specific keywords."]
	person2 = ["Just plain dialogue here."]

	tone = metrics_calculator._detect_tone(person1, person2)

	assert tone == "casual"


# ============================================================================
# SPEAKER BALANCE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_speaker_balance_perfect_50_50(metrics_calculator):
	"""Test perfectly balanced 50/50 speaker ratio."""
	person1 = ["one two three four five"]  # 5 words
	person2 = ["six seven eight nine ten"]  # 5 words

	ratio = metrics_calculator._calculate_speaker_balance_ratio(person1, person2)
	is_balanced = metrics_calculator._is_speaker_balance_good(ratio)

	assert ratio == 1.0
	assert is_balanced is True


@pytest.mark.asyncio
async def test_speaker_balance_60_40(metrics_calculator):
	"""Test balanced 60/40 speaker ratio."""
	person1 = ["one two three four five six"]  # 6 words
	person2 = ["seven eight nine ten"]  # 4 words

	ratio = metrics_calculator._calculate_speaker_balance_ratio(person1, person2)
	is_balanced = metrics_calculator._is_speaker_balance_good(ratio)

	assert ratio == 1.5  # 6/4
	assert is_balanced is True  # Within 0.3-3.33 range


@pytest.mark.asyncio
async def test_speaker_balance_80_20_imbalanced(metrics_calculator):
	"""Test imbalanced 80/20 speaker ratio."""
	person1 = ["one two three four five six seven eight"]  # 8 words
	person2 = ["nine ten"]  # 2 words

	ratio = metrics_calculator._calculate_speaker_balance_ratio(person1, person2)
	is_balanced = metrics_calculator._is_speaker_balance_good(ratio)

	assert ratio == 4.0  # 8/2
	assert is_balanced is False  # Outside 0.3-3.33 range


@pytest.mark.asyncio
async def test_speaker_balance_division_by_zero(metrics_calculator):
	"""Test speaker balance handles division by zero."""
	person1 = ["one two three"]
	person2 = []  # No words

	ratio = metrics_calculator._calculate_speaker_balance_ratio(person1, person2)
	is_balanced = metrics_calculator._is_speaker_balance_good(ratio)

	assert ratio == float('inf')
	assert is_balanced is False


@pytest.mark.asyncio
async def test_speaker_balance_30_70_edge_case(metrics_calculator):
	"""Test speaker balance at 30/70 edge (just balanced)."""
	person1 = ["one two three"]  # 3 words
	person2 = ["four five six seven eight nine ten"]  # 7 words

	ratio = metrics_calculator._calculate_speaker_balance_ratio(person1, person2)
	is_balanced = metrics_calculator._is_speaker_balance_good(ratio)

	assert abs(ratio - 0.43) < 0.01  # 3/7 ≈ 0.43
	assert is_balanced is True  # Within range


# ============================================================================
# BANTER DETECTION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_dialogue_turns_count(metrics_calculator):
	"""Test dialogue turn counting."""
	person1 = ["First", "Third", "Fifth"]
	person2 = ["Second", "Fourth"]

	turns = metrics_calculator._count_dialogue_turns(person1, person2)

	# Should alternate: P1 -> P2 -> P1 -> P2 -> P1 = 4 transitions
	assert turns == 4


@pytest.mark.asyncio
async def test_max_monologue_detection(metrics_calculator):
	"""Test max monologue word count detection."""
	person1 = ["short"]  # 1 word
	person2 = ["This is a much longer monologue segment with many words"]  # 10 words

	max_mono = metrics_calculator._find_max_monologue(person1, person2)

	assert max_mono == 10


@pytest.mark.asyncio
async def test_good_banter_detection(metrics_calculator):
	"""Test good banter detection (short exchanges, many turns)."""
	max_mono = 150  # Under 200 words
	turns = 10  # More than 5 turns

	has_good_banter = metrics_calculator._detect_good_banter(max_mono, turns)

	assert has_good_banter is True


@pytest.mark.asyncio
async def test_poor_banter_long_monologue(metrics_calculator):
	"""Test poor banter detection (long monologue)."""
	max_mono = 250  # Over 200 words
	turns = 10  # Good turns, but monologue too long

	has_good_banter = metrics_calculator._detect_good_banter(max_mono, turns)

	assert has_good_banter is False


@pytest.mark.asyncio
async def test_poor_banter_few_turns(metrics_calculator):
	"""Test poor banter detection (too few turns)."""
	max_mono = 150  # Short exchanges
	turns = 3  # Too few turns

	has_good_banter = metrics_calculator._detect_good_banter(max_mono, turns)

	assert has_good_banter is False


@pytest.mark.asyncio
async def test_banter_edge_case_exactly_200_words(metrics_calculator):
	"""Test banter detection at exactly 200 words (should be good)."""
	max_mono = 200  # Exactly 200
	turns = 5  # Exactly 5

	has_good_banter = metrics_calculator._detect_good_banter(max_mono, turns)

	assert has_good_banter is True


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

@pytest.mark.asyncio
@patch('src.services.quality_metrics_service.QualityMetricsCalculator._read_transcript_file')
async def test_calculate_metrics_full_integration(mock_read, metrics_calculator, balanced_transcript):
	"""Test full metrics calculation with balanced transcript."""
	mock_read.return_value = balanced_transcript

	metrics = await metrics_calculator.calculate_metrics("test-episode-id")

	assert isinstance(metrics, QualityMetrics)
	assert metrics.total_words > 0
	assert metrics.duration_estimate_minutes > 0
	assert 0.0 <= metrics.coherence_score <= 1.0
	assert metrics.tone in ["casual", "academic", "humorous"]
	assert metrics.speaker_balance_ratio > 0
	assert isinstance(metrics.is_balanced, bool)
	assert metrics.dialogue_turns > 0
	assert metrics.max_monologue_words > 0
	assert isinstance(metrics.has_good_banter, bool)


@pytest.mark.asyncio
@patch('src.services.quality_metrics_service.QualityMetricsCalculator._read_transcript_file')
@patch('src.services.quality_metrics_service.get_episode_by_id')
@patch('src.services.quality_metrics_service.update_episode')
async def test_calculate_and_store_metrics(
	mock_update, mock_get_episode, mock_read,
	metrics_calculator, mock_db, sample_episode, balanced_transcript
):
	"""Test metrics calculation and storage in generation_progress JSONB."""
	mock_read.return_value = balanced_transcript
	mock_get_episode.return_value = sample_episode

	episode_id = str(sample_episode.id)
	metrics = await metrics_calculator.calculate_and_store_metrics(mock_db, episode_id)

	# Verify metrics were calculated
	assert isinstance(metrics, QualityMetrics)

	# Verify episode was fetched
	mock_get_episode.assert_called_once_with(mock_db, episode_id)

	# Verify update_episode was called with quality_metrics in generation_progress
	mock_update.assert_called_once()
	call_args = mock_update.call_args
	assert call_args[0][0] == mock_db
	assert call_args[0][1] == episode_id

	updated_data = call_args[0][2]
	assert "generation_progress" in updated_data
	assert "quality_metrics" in updated_data["generation_progress"]

	quality_metrics = updated_data["generation_progress"]["quality_metrics"]
	assert quality_metrics["total_words"] == metrics.total_words
	assert quality_metrics["tone"] == metrics.tone
	assert quality_metrics["is_balanced"] == metrics.is_balanced


@pytest.mark.asyncio
@patch('src.services.quality_metrics_service.QualityMetricsCalculator._read_transcript_file')
async def test_metrics_with_imbalanced_transcript(mock_read, metrics_calculator, imbalanced_transcript):
	"""Test metrics calculation with imbalanced transcript."""
	mock_read.return_value = imbalanced_transcript

	metrics = await metrics_calculator.calculate_metrics("test-id")

	# Should detect imbalance
	assert metrics.is_balanced is False
	assert metrics.speaker_balance_ratio > 3.33  # Person1 dominates


@pytest.mark.asyncio
@patch('src.services.quality_metrics_service.QualityMetricsCalculator._read_transcript_file')
async def test_metrics_with_long_monologue(mock_read, metrics_calculator, long_monologue_transcript):
	"""Test metrics with long monologue transcript (poor banter)."""
	mock_read.return_value = long_monologue_transcript

	metrics = await metrics_calculator.calculate_metrics("test-id")

	# Should detect poor banter
	assert metrics.has_good_banter is False
	assert metrics.max_monologue_words > 200


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

@pytest.mark.asyncio
@patch('src.services.quality_metrics_service.Path')
async def test_missing_transcript_file_raises_error(mock_path, metrics_calculator):
	"""Test missing transcript file raises FileNotFoundError."""
	mock_path_instance = MagicMock()
	mock_path_instance.exists.return_value = False
	mock_path.return_value = mock_path_instance

	with pytest.raises(FileNotFoundError) as exc_info:
		await metrics_calculator.calculate_metrics("nonexistent-id")

	assert "Transcript file not found" in str(exc_info.value)


@pytest.mark.asyncio
@patch('src.services.quality_metrics_service.get_episode_by_id')
async def test_invalid_episode_id_raises_error(mock_get_episode, metrics_calculator, mock_db):
	"""Test invalid episode ID raises ValueError."""
	mock_get_episode.return_value = None

	with pytest.raises(ValueError) as exc_info:
		await metrics_calculator.calculate_and_store_metrics(mock_db, "invalid-id")

	assert "Episode" in str(exc_info.value)
	assert "not found" in str(exc_info.value)


@pytest.mark.asyncio
@patch('src.services.quality_metrics_service.QualityMetricsCalculator._read_transcript_file')
async def test_empty_transcript_raises_error(mock_read, metrics_calculator):
	"""Test empty transcript (no dialogue) raises ValueError."""
	mock_read.return_value = "<root></root>"

	with pytest.raises(ValueError) as exc_info:
		await metrics_calculator.calculate_metrics("empty-id")

	assert "no valid Person1 or Person2 dialogue" in str(exc_info.value)


# ============================================================================
# DATA STRUCTURE TESTS
# ============================================================================

def test_quality_metrics_to_dict():
	"""Test QualityMetrics to_dict conversion."""
	metrics = QualityMetrics(
		total_words=1500,
		duration_estimate_minutes=10.0,
		coherence_score=0.75,
		tone="casual",
		speaker_balance_ratio=1.2,
		is_balanced=True,
		max_monologue_words=150,
		dialogue_turns=20,
		has_good_banter=True
	)

	metrics_dict = metrics.to_dict()

	assert metrics_dict["total_words"] == 1500
	assert metrics_dict["duration_estimate_minutes"] == 10.0
	assert metrics_dict["coherence_score"] == 0.75
	assert metrics_dict["tone"] == "casual"
	assert metrics_dict["speaker_balance_ratio"] == 1.2
	assert metrics_dict["is_balanced"] is True
	assert metrics_dict["max_monologue_words"] == 150
	assert metrics_dict["dialogue_turns"] == 20
	assert metrics_dict["has_good_banter"] is True
