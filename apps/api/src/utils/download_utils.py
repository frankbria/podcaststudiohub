"""
Utility functions for audio file download operations.

Provides helpers for:
- Filename sanitization and generation
- HTTP Range header parsing (RFC 7233)
- S3 streaming with range support
"""

import os
import re
import asyncio
from typing import AsyncIterator


def is_within_dir(path: str, root: str) -> bool:
	"""True if ``path`` resolves to a location inside ``root``.

	Defense-in-depth for the no-S3 download fallback: only files under the
	configured audio storage root may be streamed from disk, so a corrupted or
	mis-written ``file_path`` can never expose an arbitrary local file (issue
	#292). Uses ``realpath`` so symlinks can't escape the root.
	"""
	if not path:
		return False
	root_real = os.path.realpath(root)
	path_real = os.path.realpath(path)
	return os.path.commonpath([root_real, path_real]) == root_real


def sanitize_filename(filename: str) -> str:
	"""
	Sanitize a string for use as a filename.

	Removes characters invalid on common filesystems (<>:"/\\|?*),
	replaces spaces with underscores, and limits length to 255 characters.

	Args:
		filename: Raw filename string to sanitize.

	Returns:
		Sanitized filename string, or 'episode' if result is empty.
	"""
	# Remove invalid filesystem characters
	sanitized = re.sub(r'[<>:"/\\|?*]', '', filename)
	# Replace spaces with underscores
	sanitized = sanitized.replace(' ', '_')
	# Limit length
	sanitized = sanitized[:255]
	# Return fallback if empty after sanitization
	return sanitized if sanitized else "episode"


def parse_range_header(range_header: str, total_size: int) -> tuple[int, int]:
	"""
	Parse HTTP Range header per RFC 7233.

	Supports:
	- Absolute range: "bytes=0-1023"
	- Open-ended range: "bytes=1024-" (from 1024 to end)
	- Suffix range: "bytes=-512" (last 512 bytes)

	Args:
		range_header: The Range header value (e.g., "bytes=0-1023").
		total_size: Total file size in bytes.

	Returns:
		Tuple of (start_byte, end_byte), both inclusive.

	Raises:
		ValueError: If the range format is invalid or out of bounds.
	"""
	if not range_header or not range_header.startswith("bytes="):
		raise ValueError(f"Invalid range header format: {range_header!r}")

	range_spec = range_header[6:]  # Strip "bytes="
	parts = range_spec.split("-")

	if len(parts) != 2:
		raise ValueError(f"Invalid range format: {range_header!r}")

	start_str, end_str = parts

	if not start_str and not end_str:
		raise ValueError("Invalid range: both start and end are missing")

	if not start_str:
		# Suffix range: "-N" means last N bytes
		suffix_length = int(end_str)
		start = max(0, total_size - suffix_length)
		end = total_size - 1
	else:
		start = int(start_str)
		end = int(end_str) if end_str else total_size - 1

	if start > end:
		raise ValueError(f"Range start {start} > end {end}")

	if start >= total_size:
		raise ValueError(f"Range start {start} >= total size {total_size}")

	if end >= total_size:
		raise ValueError(f"Range end {end} >= total size {total_size}")

	return start, end


def get_episode_filename(episode) -> str:
	"""
	Generate a sanitized downloadable filename from episode metadata.

	Format:
	- With episode number: "{episode_number:03d}_{title}.mp3"
	- Without episode number: "{title}.mp3"
	- Fallback: "episode.mp3"

	Args:
		episode: Episode model instance with episode_number and episode_metadata.

	Returns:
		Sanitized filename string ending with ".mp3".
	"""
	metadata = episode.episode_metadata or {}
	title = metadata.get("title", "") if metadata else ""
	episode_number = episode.episode_number

	sanitized_title = sanitize_filename(title) if title else ""

	if episode_number is not None and sanitized_title:
		return f"{episode_number:03d}_{sanitized_title}.mp3"
	elif sanitized_title:
		return f"{sanitized_title}.mp3"
	else:
		return "episode.mp3"


async def iter_local_file(
	path: str,
	start: int = 0,
	end: int | None = None,
	chunk_size: int = 8192,
) -> AsyncIterator[bytes]:
	"""Async generator that streams a local file in chunks, with optional range.

	Filesystem analogue of ``iter_s3_body`` for the no-S3 download path (issue
	#292). Streams bytes ``[start, end]`` inclusive (``end=None`` means to EOF),
	offloading blocking reads via ``asyncio.to_thread`` so the event loop is not
	blocked.

	Args:
		path: Local filesystem path to the audio file.
		start: First byte offset to read (inclusive).
		end: Last byte offset to read (inclusive), or None for end of file.
		chunk_size: Number of bytes per chunk (default 8KB).

	Yields:
		Bytes chunks from the file within the requested range.
	"""
	def _open():
		f = open(path, "rb")
		if start:
			f.seek(start)
		return f

	f = await asyncio.to_thread(_open)
	try:
		remaining = None if end is None else (end - start + 1)
		while remaining is None or remaining > 0:
			to_read = chunk_size if remaining is None else min(chunk_size, remaining)
			chunk = await asyncio.to_thread(f.read, to_read)
			if not chunk:
				break
			if remaining is not None:
				remaining -= len(chunk)
			yield chunk
	finally:
		await asyncio.to_thread(f.close)


async def iter_s3_body(body, chunk_size: int = 8192) -> AsyncIterator[bytes]:
	"""
	Async generator that yields chunks from an S3 response body.

	Reads from the S3 StreamingBody in chunks to avoid loading the
	entire file into memory.

	Args:
		body: S3 response body (StreamingBody).
		chunk_size: Number of bytes per chunk (default 8KB).

	Yields:
		Bytes chunks from the S3 body.
	"""
	while True:
		chunk = await asyncio.to_thread(body.read, chunk_size)
		if not chunk:
			break
		yield chunk
