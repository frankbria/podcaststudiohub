"""
Unit tests for EpisodeLayout schemas and validation logic.

Tests schema-level validation without requiring a database connection.
"""

import pytest
from uuid import uuid4
from pydantic import ValidationError

from src.schemas.episode_layout import (
	LayoutSegment,
	LayoutConfig,
	EpisodeLayoutCreate,
	EpisodeLayoutUpdate,
)


# ============================================================================
# LayoutSegment tests
# ============================================================================

def test_segment_main_content_valid():
	"""Valid main_content segment."""
	seg = LayoutSegment(type="main_content", position="auto", order=1)
	assert seg.type == "main_content"
	assert seg.position == "auto"


def test_segment_snippet_requires_snippet_id():
	"""Snippet segment without snippet_id should fail."""
	with pytest.raises(ValidationError) as exc:
		LayoutSegment(type="snippet", position="pre-roll", order=1)
	assert "snippet_id" in str(exc.value).lower()


def test_segment_snippet_valid():
	"""Valid snippet segment with snippet_id."""
	snippet_id = uuid4()
	seg = LayoutSegment(type="snippet", snippet_id=snippet_id, position="pre-roll", order=1)
	assert seg.snippet_id == snippet_id


def test_segment_position_pre_roll():
	"""pre-roll position is valid."""
	seg = LayoutSegment(type="snippet", snippet_id=uuid4(), position="pre-roll", order=1)
	assert seg.position == "pre-roll"


def test_segment_position_post_roll():
	"""post-roll position is valid."""
	seg = LayoutSegment(type="snippet", snippet_id=uuid4(), position="post-roll", order=1)
	assert seg.position == "post-roll"


def test_segment_position_auto():
	"""auto position is valid."""
	seg = LayoutSegment(type="main_content", position="auto", order=1)
	assert seg.position == "auto"


def test_segment_position_timestamp_valid():
	"""Valid timestamp positions."""
	for ts in ["0:30", "1:00", "10:59", "0:00.500"]:
		seg = LayoutSegment(type="main_content", position=ts, order=1)
		assert seg.position == ts


def test_segment_position_invalid():
	"""Invalid position format should fail."""
	with pytest.raises(ValidationError):
		LayoutSegment(type="main_content", position="invalid-position", order=1)


def test_segment_position_invalid_seconds():
	"""Timestamp with seconds >= 60 should fail."""
	with pytest.raises(ValidationError):
		LayoutSegment(type="main_content", position="0:60", order=1)


def test_segment_order_zero_invalid():
	"""Order must be >= 1."""
	with pytest.raises(ValidationError):
		LayoutSegment(type="main_content", position="auto", order=0)


# ============================================================================
# LayoutConfig tests
# ============================================================================

def test_layout_config_valid_minimal():
	"""Minimal valid config with one main_content."""
	config = LayoutConfig(
		segments=[
			LayoutSegment(type="main_content", position="auto", order=1)
		]
	)
	assert len(config.segments) == 1
	assert config.auto_normalize is True
	assert config.crossfade_duration == 0.5


def test_layout_config_no_main_content():
	"""Config without main_content segment should fail."""
	with pytest.raises(ValidationError) as exc:
		LayoutConfig(
			segments=[
				LayoutSegment(type="snippet", snippet_id=uuid4(), position="pre-roll", order=1)
			]
		)
	assert "main_content" in str(exc.value).lower()


def test_layout_config_multiple_main_content():
	"""Config with multiple main_content segments should fail."""
	with pytest.raises(ValidationError) as exc:
		LayoutConfig(
			segments=[
				LayoutSegment(type="main_content", position="auto", order=1),
				LayoutSegment(type="main_content", position="auto", order=2),
			]
		)
	assert "main_content" in str(exc.value).lower()


def test_layout_config_non_consecutive_order():
	"""Non-consecutive segment ordering should fail."""
	with pytest.raises(ValidationError) as exc:
		LayoutConfig(
			segments=[
				LayoutSegment(type="snippet", snippet_id=uuid4(), position="pre-roll", order=1),
				LayoutSegment(type="main_content", position="auto", order=3),  # gap at 2
			]
		)
	assert "consecutive" in str(exc.value).lower()


def test_layout_config_ordering_zero_indexed():
	"""0-indexed ordering should fail (must start at 1)."""
	with pytest.raises(ValidationError):
		LayoutConfig(
			segments=[
				LayoutSegment(type="main_content", position="auto", order=0),
			]
		)


def test_layout_config_crossfade_out_of_range():
	"""Crossfade duration > 5.0 should fail."""
	with pytest.raises(ValidationError):
		LayoutConfig(
			segments=[LayoutSegment(type="main_content", position="auto", order=1)],
			crossfade_duration=10.0
		)


def test_layout_config_crossfade_negative():
	"""Crossfade duration < 0.0 should fail."""
	with pytest.raises(ValidationError):
		LayoutConfig(
			segments=[LayoutSegment(type="main_content", position="auto", order=1)],
			crossfade_duration=-1.0
		)


def test_layout_config_three_segments():
	"""Valid three-segment intro-main-outro config."""
	config = LayoutConfig(
		segments=[
			LayoutSegment(type="snippet", snippet_id=uuid4(), position="pre-roll", order=1),
			LayoutSegment(type="main_content", position="auto", order=2),
			LayoutSegment(type="snippet", snippet_id=uuid4(), position="post-roll", order=3),
		],
		auto_normalize=True,
		crossfade_duration=1.0
	)
	assert len(config.segments) == 3


# ============================================================================
# EpisodeLayoutCreate tests
# ============================================================================

def test_create_schema_valid():
	"""Valid EpisodeLayoutCreate schema."""
	layout = EpisodeLayoutCreate(
		name="Test Layout",
		layout_config=LayoutConfig(
			segments=[LayoutSegment(type="main_content", position="auto", order=1)]
		)
	)
	assert layout.name == "Test Layout"
	assert layout.is_default is False
	assert layout.project_id is None


def test_create_schema_name_required():
	"""Name is required."""
	with pytest.raises(ValidationError):
		EpisodeLayoutCreate(
			layout_config=LayoutConfig(
				segments=[LayoutSegment(type="main_content", position="auto", order=1)]
			)
		)


def test_create_schema_name_too_long():
	"""Name exceeding 255 chars should fail."""
	with pytest.raises(ValidationError):
		EpisodeLayoutCreate(
			name="x" * 256,
			layout_config=LayoutConfig(
				segments=[LayoutSegment(type="main_content", position="auto", order=1)]
			)
		)


def test_create_schema_name_empty():
	"""Empty name should fail."""
	with pytest.raises(ValidationError):
		EpisodeLayoutCreate(
			name="",
			layout_config=LayoutConfig(
				segments=[LayoutSegment(type="main_content", position="auto", order=1)]
			)
		)


# ============================================================================
# EpisodeLayoutUpdate tests
# ============================================================================

def test_update_schema_all_optional():
	"""All fields in update schema are optional."""
	update = EpisodeLayoutUpdate()
	assert update.name is None
	assert update.description is None
	assert update.layout_config is None
	assert update.is_default is None


def test_update_schema_partial():
	"""Partial update with only name."""
	update = EpisodeLayoutUpdate(name="Updated")
	assert update.name == "Updated"


def test_update_schema_name_too_long():
	"""Name exceeding 255 chars should fail in update schema too."""
	with pytest.raises(ValidationError):
		EpisodeLayoutUpdate(name="x" * 256)
