"""
Unit tests for download utility functions.

Tests run without a database by importing utility functions directly.
Covers filename sanitization, range header parsing, and episode filename generation.
"""

import pytest
from unittest.mock import MagicMock

from src.utils.download_utils import sanitize_filename, parse_range_header, get_episode_filename


# ============================================================================
# sanitize_filename tests
# ============================================================================

class TestSanitizeFilename:
	"""Unit tests for filename sanitization."""

	def test_removes_invalid_chars(self):
		"""Removes characters invalid in filenames."""
		result = sanitize_filename('my<>:"/\\|?*file')
		for char in '<>:"/\\|?*':
			assert char not in result

	def test_replaces_spaces_with_underscores(self):
		"""Spaces are replaced with underscores."""
		result = sanitize_filename("My Episode Title")
		assert " " not in result
		assert "_" in result

	def test_truncates_long_filenames(self):
		"""Filenames longer than 255 chars are truncated."""
		long_name = "a" * 300
		result = sanitize_filename(long_name)
		assert len(result) <= 255

	def test_empty_string_returns_episode(self):
		"""Empty string returns fallback 'episode'."""
		result = sanitize_filename("")
		assert result == "episode"

	def test_only_invalid_chars_returns_episode(self):
		"""String with only invalid chars returns fallback 'episode'."""
		result = sanitize_filename("<>:/\\|?*")
		assert result == "episode"

	def test_normal_filename_unchanged(self):
		"""Normal alphanumeric filename passes through."""
		result = sanitize_filename("MyPodcast123")
		assert result == "MyPodcast123"

	def test_preserves_hyphens_and_dots(self):
		"""Hyphens and dots are preserved."""
		result = sanitize_filename("my-podcast.mp3")
		assert "-" in result
		assert "." in result

	def test_preserves_underscores(self):
		"""Underscores are preserved."""
		result = sanitize_filename("my_podcast")
		assert result == "my_podcast"


# ============================================================================
# parse_range_header tests
# ============================================================================

class TestParseRangeHeader:
	"""Unit tests for HTTP Range header parsing."""

	def test_absolute_range(self):
		"""Parses absolute range 'bytes=0-1023'."""
		start, end = parse_range_header("bytes=0-1023", 5242880)
		assert start == 0
		assert end == 1023

	def test_mid_range(self):
		"""Parses range starting in the middle."""
		start, end = parse_range_header("bytes=1024-2047", 5242880)
		assert start == 1024
		assert end == 2047

	def test_open_ended_range(self):
		"""Parses open-ended range 'bytes=1024-' (from 1024 to end)."""
		start, end = parse_range_header("bytes=1024-", 5242880)
		assert start == 1024
		assert end == 5242879  # total_size - 1

	def test_suffix_range(self):
		"""Parses suffix range 'bytes=-512' (last 512 bytes)."""
		start, end = parse_range_header("bytes=-512", 5242880)
		assert start == 5242368  # 5242880 - 512
		assert end == 5242879

	def test_suffix_range_larger_than_file(self):
		"""Suffix range larger than file starts at byte 0."""
		start, end = parse_range_header("bytes=-99999", 100)
		assert start == 0
		assert end == 99

	def test_invalid_format_raises_value_error(self):
		"""Invalid format raises ValueError."""
		with pytest.raises(ValueError):
			parse_range_header("invalid", 1000)

	def test_missing_bytes_prefix_raises_value_error(self):
		"""Missing 'bytes=' prefix raises ValueError."""
		with pytest.raises(ValueError):
			parse_range_header("0-1023", 1000)

	def test_start_greater_than_end_raises_value_error(self):
		"""Range where start > end raises ValueError."""
		with pytest.raises(ValueError):
			parse_range_header("bytes=1024-512", 5000)

	def test_start_beyond_file_size_raises_value_error(self):
		"""Range starting beyond file size raises ValueError."""
		with pytest.raises(ValueError):
			parse_range_header("bytes=5242880-5242900", 5242880)

	def test_end_beyond_file_size_raises_value_error(self):
		"""Range ending beyond file size raises ValueError."""
		with pytest.raises(ValueError):
			parse_range_header("bytes=0-9999999", 5000)

	def test_exact_last_byte(self):
		"""Range for the exact last byte is valid."""
		start, end = parse_range_header("bytes=99-99", 100)
		assert start == 99
		assert end == 99

	def test_full_file_range(self):
		"""Range covering full file."""
		start, end = parse_range_header("bytes=0-99", 100)
		assert start == 0
		assert end == 99

	def test_empty_string_raises_value_error(self):
		"""Empty string raises ValueError."""
		with pytest.raises(ValueError):
			parse_range_header("", 1000)


# ============================================================================
# get_episode_filename tests
# ============================================================================

class TestGetEpisodeFilename:
	"""Unit tests for episode filename generation."""

	def _make_episode(self, title=None, episode_number=None, metadata=None):
		episode = MagicMock()
		episode.episode_number = episode_number
		if metadata is not None:
			episode.episode_metadata = metadata
		elif title is not None:
			episode.episode_metadata = {"title": title}
		else:
			episode.episode_metadata = {}
		return episode

	def test_filename_with_episode_number(self):
		"""Filename includes zero-padded episode number when available."""
		episode = self._make_episode(title="My First Episode", episode_number=1)
		result = get_episode_filename(episode)
		assert result == "001_My_First_Episode.mp3"

	def test_filename_without_episode_number(self):
		"""Filename without episode number uses title only."""
		episode = self._make_episode(title="My Episode", episode_number=None)
		result = get_episode_filename(episode)
		assert result == "My_Episode.mp3"

	def test_filename_default_when_no_title(self):
		"""Default filename when episode metadata has no title."""
		episode = self._make_episode(title=None, episode_number=None)
		result = get_episode_filename(episode)
		assert result == "episode.mp3"

	def test_filename_sanitizes_special_chars(self):
		"""Special characters in title are sanitized."""
		episode = self._make_episode(title='Episode: "The First"', episode_number=2)
		result = get_episode_filename(episode)
		assert '"' not in result
		assert ":" not in result
		assert result.endswith(".mp3")

	def test_filename_ends_with_mp3(self):
		"""Filename always ends with .mp3."""
		episode = self._make_episode(title="Test", episode_number=5)
		result = get_episode_filename(episode)
		assert result.endswith(".mp3")

	def test_episode_number_zero_padded_to_three_digits(self):
		"""Episode number is zero-padded to 3 digits."""
		episode = self._make_episode(title="Ep", episode_number=42)
		result = get_episode_filename(episode)
		assert result.startswith("042_")

	def test_large_episode_number(self):
		"""Large episode numbers work correctly (no truncation)."""
		episode = self._make_episode(title="Ep", episode_number=1000)
		result = get_episode_filename(episode)
		assert result.startswith("1000_")

	def test_none_episode_metadata(self):
		"""None episode_metadata uses default filename."""
		episode = self._make_episode(metadata=None)
		episode.episode_number = None
		episode.episode_metadata = None
		result = get_episode_filename(episode)
		assert result == "episode.mp3"

	def test_empty_title_uses_default(self):
		"""Empty title string falls back to episode.mp3."""
		episode = self._make_episode(title="", episode_number=None)
		result = get_episode_filename(episode)
		assert result == "episode.mp3"
