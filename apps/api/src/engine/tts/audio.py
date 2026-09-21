"""Audio assembly for the TTS layer (issue #542).

Every backend produces per-turn or per-batch MP3 blobs that have to become one
file. podcastfy did this twice, differently and in two places: the multi-speaker
path exported at 320k, the per-turn path took pydub's default, and the
per-chunk merge wrote `temp_chunk_{i}.mp3` into the process working directory.

One helper, one bitrate, everything under the caller's workdir.
"""
import logging
from pathlib import Path
from typing import Iterable

from src.config import settings
from src.engine.tts.base import TTSError

logger = logging.getLogger(__name__)


def concat_to_mp3(segments: Iterable[bytes], workdir: Path, name: str) -> Path:
    """Join audio blobs in order into one MP3 at ``workdir/name``.

    ``segments`` are whole encoded audio files, not raw frames — every provider
    returns an encoded blob — so pydub decodes each one before joining. That
    needs ffmpeg on the host, which is why the unit tests patch
    ``pydub.AudioSegment`` rather than doing real audio work: CI has no ffmpeg,
    and `pytest.ini` already carries the matching pydub warning filter.
    """
    # Imported lazily so that merely importing the engine does not require
    # pydub/ffmpeg to be present — the same reason `audio_utils` defers it.
    from pydub import AudioSegment

    workdir.mkdir(parents=True, exist_ok=True)
    output = workdir / name

    combined = AudioSegment.empty()
    count = 0
    for blob in segments:
        if not blob:
            continue
        combined += AudioSegment.from_file(_as_stream(blob))
        count += 1

    if count == 0:
        raise TTSError("No audio was produced for this script")

    combined.export(
        output,
        format="mp3",
        bitrate=settings.ENGINE_AUDIO_BITRATE,
    )
    logger.info("Assembled %d audio segments into %s", count, output)
    return output


def _as_stream(blob: bytes):
    import io

    return io.BytesIO(blob)
