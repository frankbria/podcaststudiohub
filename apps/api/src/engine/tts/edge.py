"""Edge TTS backend (issue #542) — the free tier, no API key needed.

podcastfy called `nest_asyncio.apply()` inside `generate_audio`
(`tts/providers/edge.py:22`), which monkey-patches the running event loop policy
*process-wide* to let a nested loop run, then drove it through the deprecated
`asyncio.get_event_loop()`. Inside a Celery worker that is a global side effect
imposed by whichever provider happened to be selected.

`asyncio.run` in a worker thread needs neither: each call gets its own loop and
disposes of it. That is also the pattern the rest of this repo already uses to
bridge sync Celery tasks into async code (`src/tasks/content_extraction.py:136`).
"""
import asyncio
import logging
from pathlib import Path

from src.engine.models import Script
from src.engine.tts.audio import concat_to_mp3
from src.engine.tts.base import (
    TTSError,
    TTSProviderError,
    VoiceConfig,
    turns_for_synthesis,
)
from src.engine.tts.openai import synthesise_concurrently

logger = logging.getLogger(__name__)


class EdgeTTS:
    """Per-turn synthesis against Microsoft Edge's read-aloud service."""

    def synthesise(
        self, script: Script, voices: VoiceConfig, workdir: Path
    ) -> Path:
        turns = turns_for_synthesis(script)
        if not turns:
            raise TTSError("Script has no speakable turns")

        workdir.mkdir(parents=True, exist_ok=True)
        options = voices.options

        def render(turn) -> bytes:
            index, speaker, text = turn
            # Inside workdir, and named by turn index so two concurrent turns
            # cannot collide — the defect podcastfy's `temp_chunk_{i}.mp3` in
            # the process cwd had.
            destination = workdir / f"turn-{index:04d}.mp3"
            try:
                asyncio.run(
                    _save(text, voices.voice_for(speaker), destination, options)
                )
            except Exception as exc:  # noqa: BLE001 — edge-tts is an unofficial client with no exception hierarchy of its own; every failure here maps to the same outcome
                raise TTSProviderError(f"Edge TTS call failed: {exc}") from exc
            return destination.read_bytes()

        segments = synthesise_concurrently(render, turns)
        return concat_to_mp3(segments, workdir, "episode.mp3")


async def _save(text: str, voice: str, destination: Path, options: dict) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(
        text,
        voice,
        rate=options.get("rate", "+0%"),
        volume=options.get("volume", "+0%"),
    )
    await communicate.save(str(destination))
