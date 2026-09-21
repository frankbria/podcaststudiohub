"""OpenAI TTS backend (issue #542).

Fixes two things podcastfy did here. It set ``openai.api_key`` as module-global
state (`tts/providers/openai.py:22`), which is process-wide, clobbers anything
else in the worker using a different key, and forecloses bring-your-own-key
entirely — a scoped client costs nothing and does not. And it synthesised one
turn at a time in a plain loop, each a blocking round trip, so a forty-turn
episode paid forty round trips end to end.
"""
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import openai

from src.config import settings
from src.engine.tts.audio import concat_to_mp3
from src.engine.tts.base import (
    TTSError,
    TTSProviderError,
    VoiceConfig,
    turns_for_synthesis,
)
from src.engine.models import Script

logger = logging.getLogger(__name__)


class OpenAITTS:
    """Per-turn synthesis against ``audio.speech.create``."""

    def synthesise(
        self, script: Script, voices: VoiceConfig, workdir: Path
    ) -> Path:
        if not settings.OPENAI_API_KEY:
            raise TTSError("OPENAI_API_KEY is not set; cannot synthesise audio")

        turns = turns_for_synthesis(script)
        if not turns:
            raise TTSError("Script has no speakable turns")

        # Scoped to this call. Never `openai.api_key = ...`: that is the global
        # this backend exists to stop setting, and a test asserts it stays unset.
        client = openai.OpenAI(
            api_key=settings.OPENAI_API_KEY,
            # Seconds — see the note in src/engine/llm.py; openai-python hands
            # this to httpx, whose timeouts are seconds, unlike google-genai's.
            timeout=settings.OPENAI_API_TIMEOUT,
        )
        model = voices.model or settings.ENGINE_OPENAI_TTS_MODEL

        def render(turn) -> bytes:
            _, speaker, text = turn
            # `speed` is bounded 0.25-4.0 at write time, which is exactly the
            # speech API's own range -- the field exists to be forwarded.
            extra = (
                {"speed": voices.options["speed"]}
                if "speed" in voices.options
                else {}
            )
            try:
                response = client.audio.speech.create(
                    model=model,
                    voice=voices.voice_for(speaker),
                    input=text,
                    response_format="mp3",
                    **extra,
                )
            except openai.OpenAIError as exc:
                raise TTSProviderError(f"OpenAI TTS call failed: {exc}") from exc
            return response.content

        segments = synthesise_concurrently(render, turns)
        return concat_to_mp3(segments, workdir, "episode.mp3")


def synthesise_concurrently(render, turns) -> list:
    """Render turns in parallel, bounded, preserving script order.

    Shared by every per-turn backend. The bound matters twice over: providers
    rate-limit, and this runs inside a Celery prefork worker, so the threads are
    per-process and an unbounded pool would multiply by the worker count.
    ``ThreadPoolExecutor.map`` yields in input order, so the result is already
    in script order — order is the one thing that must not be raced.
    """
    workers = max(1, min(settings.ENGINE_TTS_MAX_CONCURRENCY, len(turns)))
    if workers == 1:
        return [render(turn) for turn in turns]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(render, turns))
