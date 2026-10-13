"""ElevenLabs backend (issue #542) — Eleven v3 Text-to-Dialogue.

This is the capability podcastfy could not reach. It called the legacy
``client.generate()`` shim one turn at a time on ``eleven_multilingual_v2``
(`tts/providers/elevenlabs.py:21`), so every turn was synthesised in isolation
with no knowledge of the line before it.

Text-to-Dialogue takes the turns *together* — each with its own ``voice_id`` —
and renders them as one conversation, which is what makes interruptions,
reactions and timing sound like people rather than two alternating monologues.
It is also the only path that honours audio tags (``[laughs]``, ``[curious]``),
and only on v3 models.

Requires ``elevenlabs>=2.x``: ``text_to_dialogue`` does not exist in 1.x, and
2.x dropped ``generate()``, the call the previous engine (podcastfy, capped at
``<2``) relied on; that cap is gone with it (#543).
"""
import logging
from pathlib import Path
from typing import Iterator, Optional

import elevenlabs
import httpx
from elevenlabs.client import ElevenLabs
from elevenlabs.core.api_error import ApiError

from src.config import settings
from src.engine.llm import is_retryable_status
from src.engine.models import Script
from src.engine.tts.audio import concat_to_mp3
from src.engine.tts.base import (
    TTSError,
    TTSProviderError,
    VoiceConfig,
    batch_turns,
    turns_for_synthesis,
    with_retries,
)

logger = logging.getLogger(__name__)


class ElevenLabsTTS:
    """Whole-conversation synthesis via Text-to-Dialogue."""

    def synthesise(
        self, script: Script, voices: VoiceConfig, workdir: Path
    ) -> Path:
        if not settings.ELEVENLABS_API_KEY:
            raise TTSError(
                "ELEVENLABS_API_KEY is not set; cannot synthesise audio"
            )

        turns = turns_for_synthesis(script)
        if not turns:
            raise TTSError("Script has no speakable turns")

        client = ElevenLabs(api_key=settings.ELEVENLABS_API_KEY)
        model = _dialogue_model(voices.model)

        segments = []
        for batch in batch_turns(
            turns,
            settings.ENGINE_ELEVENLABS_CHAR_LIMIT,
            size=lambda turn: len(turn[2]),
        ):
            inputs = [
                elevenlabs.DialogueInput(
                    text=text, voice_id=voices.voice_for(speaker)
                )
                for _, speaker, text in batch
            ]
            segments.append(with_retries(lambda: _render_dialogue(client, inputs, model)))

        logger.info(
            "Synthesised %d turns as %d dialogue request(s)", len(turns), len(segments)
        )
        return concat_to_mp3(segments, workdir, "episode.mp3")


def _render_dialogue(client, inputs, model: str) -> bytes:
    """One Text-to-Dialogue request, collected to bytes."""
    try:
        audio = client.text_to_dialogue.convert(
            inputs=inputs,
            model_id=model,
            output_format=settings.ENGINE_ELEVENLABS_OUTPUT_FORMAT,
            # The engine owns retries (with_retries); the SDK's default two
            # would stack under it (#620).
            request_options={"max_retries": 0},
        )
        # Collected inside the try on purpose: `convert` returns a lazy
        # chunk iterator, so the HTTP body transfer happens here, not
        # above. A reset or read timeout part-way through the body
        # would otherwise escape as a raw httpx error.
        return _collect(audio)
    except TTSProviderError:
        raise
    except Exception as exc:  # noqa: BLE001 — the SDK raises ApiError subclasses plus bare httpx errors; every one maps to the same outcome for the caller
        raise TTSProviderError(
            f"ElevenLabs Text-to-Dialogue call failed: {exc}",
            retryable=_eleven_retryable(exc),
        ) from exc


def _eleven_retryable(exc: Exception) -> bool:
    """A 408/409/429/5xx or a dropped connection; never a timeout (#620)."""
    if isinstance(exc, ApiError):
        return is_retryable_status(exc.status_code)
    return isinstance(exc, httpx.TransportError) and not isinstance(exc, httpx.TimeoutException)


def _dialogue_model(stored: Optional[str]) -> str:
    """The model to send, ignoring a stored value Text-to-Dialogue cannot use.

    `model` is required at write time, so every stored row has one -- which
    makes a plain ``stored or default`` fall back never. And the app's only
    config writer still posts `eleven_multilingual_v2`
    (`apps/web/src/app/(auth)/episodes/[id]/page.tsx`), a family Text-to-Dialogue
    does not support, so honouring it would fail every real config. Audio tags
    are v3-only for the same reason.
    """
    if stored and stored.startswith("eleven_v3"):
        return stored
    if stored:
        logger.warning(
            "Stored ElevenLabs model %r does not support Text-to-Dialogue; "
            "using %s instead", stored, settings.ENGINE_ELEVENLABS_MODEL,
        )
    return settings.ENGINE_ELEVENLABS_MODEL


def _collect(audio) -> bytes:
    """The SDK returns an iterator of chunks; callers need one blob."""
    if isinstance(audio, (bytes, bytearray)):
        return bytes(audio)
    if isinstance(audio, Iterator) or hasattr(audio, "__iter__"):
        return b"".join(chunk for chunk in audio if chunk)
    raise TTSProviderError(
        f"ElevenLabs returned an unexpected audio type: {type(audio).__name__}"
    )
