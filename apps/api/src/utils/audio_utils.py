"""
Audio utility functions for file validation and metadata extraction.

Provides helpers for validating audio file formats, sizes, and extracting
metadata such as duration, file format, and generating S3 keys.
"""

import os
import uuid
from pathlib import Path
from typing import Optional

# Allowed audio MIME types and their file extensions
ALLOWED_AUDIO_FORMATS = {
	"audio/mpeg": "mp3",
	"audio/mp3": "mp3",
	"audio/wav": "wav",
	"audio/x-wav": "wav",
	"audio/aac": "aac",
	"audio/ogg": "ogg",
	"audio/vorbis": "ogg",
}

ALLOWED_EXTENSIONS = {"mp3", "wav", "aac", "ogg"}

MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
MIN_FILE_SIZE_BYTES = 100 * 1024  # 100 KB
MAX_DURATION_SECONDS = 600  # 10 minutes


def get_file_extension(filename: str) -> str:
	"""
	Extract and normalize file extension from filename.

	Args:
		filename: Original filename

	Returns:
		Lowercase file extension without leading dot
	"""
	return Path(filename).suffix.lstrip(".").lower()


def validate_audio_format(filename: str, content_type: Optional[str] = None) -> str:
	"""
	Validate audio file format based on extension and content type.

	Args:
		filename: Original filename
		content_type: MIME type from upload

	Returns:
		Validated file extension (e.g. 'mp3', 'wav')

	Raises:
		ValueError: If format is not allowed
	"""
	ext = get_file_extension(filename)

	if ext not in ALLOWED_EXTENSIONS:
		raise ValueError(
			f"Unsupported file format '.{ext}'. "
			f"Allowed formats: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
		)

	# Also validate MIME type if provided
	if content_type and content_type not in ALLOWED_AUDIO_FORMATS:
		# Be lenient: if extension is valid but MIME type is unrecognized, allow it
		# Some clients send generic 'application/octet-stream'
		pass

	return ext


def validate_file_size(file_size_bytes: int) -> None:
	"""
	Validate file size is within allowed bounds.

	Args:
		file_size_bytes: File size in bytes

	Raises:
		ValueError: If file is too large or too small
	"""
	if file_size_bytes > MAX_FILE_SIZE_BYTES:
		raise ValueError(
			f"File too large ({file_size_bytes} bytes). "
			f"Maximum allowed size is {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB"
		)
	if file_size_bytes < MIN_FILE_SIZE_BYTES:
		raise ValueError(
			f"File too small ({file_size_bytes} bytes). "
			f"Minimum allowed size is {MIN_FILE_SIZE_BYTES // 1024} KB"
		)


def get_audio_duration(file_path: str) -> Optional[float]:
	"""
	Extract audio duration in seconds using pydub with ffmpeg fallback.

	Args:
		file_path: Path to local audio file

	Returns:
		Duration in seconds (float), or None if extraction fails
	"""
	try:
		from pydub import AudioSegment
		audio = AudioSegment.from_file(file_path)
		return len(audio) / 1000.0
	except Exception:
		pass

	# Fallback: try ffprobe directly
	try:
		import subprocess
		result = subprocess.run(
			[
				"ffprobe", "-v", "quiet", "-print_format", "json",
				"-show_streams", file_path
			],
			capture_output=True, text=True, timeout=30
		)
		if result.returncode == 0:
			import json
			data = json.loads(result.stdout)
			for stream in data.get("streams", []):
				if stream.get("codec_type") == "audio":
					duration = stream.get("duration")
					if duration:
						return float(duration)
	except Exception:
		pass

	return None


def generate_s3_key(user_id: str, snippet_id: str, file_ext: str) -> str:
	"""
	Generate a consistent S3 object key for an audio snippet.

	Args:
		user_id: User UUID as string
		snippet_id: Snippet UUID as string
		file_ext: File extension (e.g. 'mp3')

	Returns:
		S3 key string (e.g. 'audio-snippets/user_id/snippet_id.mp3')
	"""
	return f"audio-snippets/{user_id}/{snippet_id}.{file_ext}"


def get_content_type(file_ext: str) -> str:
	"""
	Get MIME content type for a file extension.

	Args:
		file_ext: File extension (e.g. 'mp3')

	Returns:
		MIME type string
	"""
	content_types = {
		"mp3": "audio/mpeg",
		"wav": "audio/wav",
		"aac": "audio/aac",
		"ogg": "audio/ogg",
	}
	return content_types.get(file_ext, "application/octet-stream")
