"""
Unit tests for audio utility functions.

Tests cover:
- get_audio_duration: pydub success, pydub failure + ffprobe success (with audio
  stream), pydub + ffprobe both fail, pydub failure + ffprobe non-zero exit,
  pydub failure + ffprobe stream without duration, pydub failure + ffprobe exception
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from src.utils.audio_utils import get_audio_duration


# ===========================================================================
# get_audio_duration
# ===========================================================================


class TestGetAudioDuration:

	def test_pydub_success_returns_duration(self):
		"""When pydub succeeds, returns duration in seconds."""
		mock_audio = MagicMock()
		mock_audio.__len__ = lambda self: 5000  # 5000 ms

		with patch("pydub.AudioSegment") as mock_seg_cls:
			mock_seg_cls.from_file.return_value = mock_audio
			result = get_audio_duration("/fake/file.mp3")

		assert result == pytest.approx(5.0)

	def test_pydub_failure_ffprobe_success(self):
		"""When pydub fails, falls back to ffprobe and returns duration."""
		ffprobe_output = json.dumps({
			"streams": [
				{"codec_type": "audio", "duration": "42.5"},
			]
		})
		completed = MagicMock()
		completed.returncode = 0
		completed.stdout = ffprobe_output

		with patch("pydub.AudioSegment") as mock_seg_cls:
			mock_seg_cls.from_file.side_effect = Exception("pydub error")
			with patch("subprocess.run", return_value=completed):
				result = get_audio_duration("/fake/file.mp3")

		assert result == pytest.approx(42.5)

	def test_pydub_failure_ffprobe_non_zero_returns_none(self):
		"""When pydub fails and ffprobe returns non-zero, returns None."""
		completed = MagicMock()
		completed.returncode = 1
		completed.stdout = ""

		with patch("pydub.AudioSegment") as mock_seg_cls:
			mock_seg_cls.from_file.side_effect = Exception("pydub error")
			with patch("subprocess.run", return_value=completed):
				result = get_audio_duration("/fake/file.mp3")

		assert result is None

	def test_both_fail_returns_none(self):
		"""When both pydub and ffprobe raise exceptions, returns None."""
		with patch("pydub.AudioSegment") as mock_seg_cls:
			mock_seg_cls.from_file.side_effect = Exception("pydub error")
			with patch("subprocess.run", side_effect=Exception("ffprobe error")):
				result = get_audio_duration("/fake/file.mp3")

		assert result is None

	def test_ffprobe_stream_without_duration_returns_none(self):
		"""When ffprobe succeeds but audio stream has no duration, returns None."""
		ffprobe_output = json.dumps({
			"streams": [
				{"codec_type": "audio"},  # no 'duration' key
			]
		})
		completed = MagicMock()
		completed.returncode = 0
		completed.stdout = ffprobe_output

		with patch("pydub.AudioSegment") as mock_seg_cls:
			mock_seg_cls.from_file.side_effect = Exception("pydub error")
			with patch("subprocess.run", return_value=completed):
				result = get_audio_duration("/fake/file.mp3")

		assert result is None

	def test_ffprobe_no_audio_stream_returns_none(self):
		"""When ffprobe has no audio streams, returns None."""
		ffprobe_output = json.dumps({
			"streams": [
				{"codec_type": "video", "duration": "60.0"},
			]
		})
		completed = MagicMock()
		completed.returncode = 0
		completed.stdout = ffprobe_output

		with patch("pydub.AudioSegment") as mock_seg_cls:
			mock_seg_cls.from_file.side_effect = Exception("pydub error")
			with patch("subprocess.run", return_value=completed):
				result = get_audio_duration("/fake/file.mp3")

		assert result is None
