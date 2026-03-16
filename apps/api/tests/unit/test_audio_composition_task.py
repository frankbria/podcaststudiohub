"""
Tests for audio composition Celery task (merge_audio_snippets_task).

Covers issue #116: happy path merging, normalize/fade flags,
empty timeline edge case, and error-path return shape.
"""

import sys
import types
from unittest.mock import MagicMock, patch

from src.tasks.audio_composition import merge_audio_snippets_task


def _mock_pydub_modules():
	"""Return mocked AudioSegment class + modules dict for sys.modules patching."""
	mock_audio_segment_class = MagicMock()
	mock_pydub = types.ModuleType("pydub")
	mock_pydub.AudioSegment = mock_audio_segment_class
	return mock_audio_segment_class, {
		"pydub": mock_pydub,
		"pydub.AudioSegment": mock_audio_segment_class,
	}


def _make_mock_audio_segment(duration_ms=5000):
	"""Return a MagicMock that behaves like a pydub AudioSegment instance."""
	seg = MagicMock()
	seg.__len__ = MagicMock(return_value=duration_ms)
	seg.normalize.return_value = seg
	seg.fade_in.return_value = seg
	seg.fade_out.return_value = seg
	seg.__iadd__ = MagicMock(return_value=seg)
	return seg


class TestMergeAudioSnippetsTask:

	def test_happy_path_two_segments_merged(self):
		"""Two segments are loaded, appended, and exported as mp3."""
		mock_cls, mock_modules = _mock_pydub_modules()
		seg_instance = _make_mock_audio_segment(duration_ms=10000)
		mock_cls.from_file.return_value = seg_instance
		mock_cls.empty.return_value = seg_instance

		timeline = [
			{"file_path": "/tmp/seg1.mp3"},
			{"file_path": "/tmp/seg2.mp3"},
		]

		with patch.object(merge_audio_snippets_task, "update_state") as mock_update, \
			 patch.dict(sys.modules, mock_modules), \
			 patch("os.path.getsize", return_value=4096):

			result = merge_audio_snippets_task.run(
				episode_id="ep-001",
				timeline=timeline,
				output_path="/tmp/out.mp3",
			)

		assert result["status"] == "success"
		assert result["output_path"] == "/tmp/out.mp3"
		assert result["error"] is None
		assert result["duration_seconds"] == 10000 / 1000.0
		assert result["file_size_bytes"] == 4096
		assert mock_cls.from_file.call_count == 2
		seg_instance.export.assert_called_once_with(
			"/tmp/out.mp3", format="mp3", bitrate="192k"
		)

		# Verify progress updates were sent
		assert mock_update.call_count >= 2
		first_call = mock_update.call_args_list[0]
		assert first_call.kwargs["state"] == "PROGRESS"
		assert first_call.kwargs["meta"]["progress"] == 0
		assert first_call.kwargs["meta"]["episode_id"] == "ep-001"

	def test_normalize_and_fade_flags_applied(self):
		"""Normalize, fade_in, and fade_out are called when flags are set."""
		mock_cls, mock_modules = _mock_pydub_modules()
		seg_instance = _make_mock_audio_segment()
		mock_cls.from_file.return_value = seg_instance
		mock_cls.empty.return_value = seg_instance

		timeline = [
			{
				"file_path": "/tmp/seg.mp3",
				"normalize": True,
				"fade_in_ms": 500,
				"fade_out_ms": 300,
			},
		]

		with patch.object(merge_audio_snippets_task, "update_state"), \
			 patch.dict(sys.modules, mock_modules), \
			 patch("os.path.getsize", return_value=2048):

			result = merge_audio_snippets_task.run(
				episode_id="ep-002",
				timeline=timeline,
				output_path="/tmp/out.mp3",
			)

		assert result["status"] == "success"
		seg_instance.normalize.assert_called_once()
		seg_instance.fade_in.assert_called_once_with(500)
		seg_instance.fade_out.assert_called_once_with(300)

	def test_empty_timeline_returns_success(self):
		"""Empty timeline exports an empty AudioSegment and returns success."""
		mock_cls, mock_modules = _mock_pydub_modules()
		empty_seg = _make_mock_audio_segment(duration_ms=0)
		mock_cls.empty.return_value = empty_seg

		with patch.object(merge_audio_snippets_task, "update_state"), \
			 patch.dict(sys.modules, mock_modules), \
			 patch("os.path.getsize", return_value=0):

			result = merge_audio_snippets_task.run(
				episode_id="ep-003",
				timeline=[],
				output_path="/tmp/empty.mp3",
			)

		assert result["status"] == "success"
		assert result["duration_seconds"] == 0.0
		assert mock_cls.from_file.call_count == 0
		empty_seg.export.assert_called_once()

	def test_error_path_returns_correct_shape(self):
		"""When from_file raises, task retries and returns failed status after exhaustion."""
		mock_cls, mock_modules = _mock_pydub_modules()
		mock_cls.empty.return_value = _make_mock_audio_segment()
		mock_cls.from_file.side_effect = RuntimeError("FFmpeg not found")

		timeline = [{"file_path": "/tmp/bad.mp3"}]

		with patch.object(merge_audio_snippets_task, "update_state"), \
			 patch.dict(sys.modules, mock_modules), \
			 patch.object(
				merge_audio_snippets_task,
				"retry",
				side_effect=merge_audio_snippets_task.MaxRetriesExceededError(),
			 ):

			result = merge_audio_snippets_task.run(
				episode_id="ep-004",
				timeline=timeline,
				output_path="/tmp/out.mp3",
			)

		assert result["status"] == "failed"
		assert result["output_path"] is None
		assert result["duration_seconds"] == 0
		assert result["file_size_bytes"] == 0
		assert "FFmpeg not found" in result["error"]
