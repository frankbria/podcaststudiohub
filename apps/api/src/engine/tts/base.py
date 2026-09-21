"""Shared types for the in-repo TTS layer (issue #542).

Replaces `podcastfy.text_to_speech` and `podcastfy/tts/providers/*`, whose
interface forced every defect this package exists to avoid: providers returned
bare `bytes` with no say in where files landed, so one of them wrote
`temp_chunk_{i}.mp3` into the process working directory (a live collision under
the prefork pool), and another computed its temp directory *inside* the
installed package — the venv currently holds 12 leftover MP3s, 1.1 MB, as proof.

The fix is in the signature: a backend is handed the `workdir` it must write
under, and hands back the one file it produced. Nothing else is negotiable.
"""
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field

from src.engine.llm import EngineError
from src.engine.models import Script

# The five values `tts_configurations.provider` is constrained to by
# `src/schemas/tts_configuration.py`. Kept in sync deliberately rather than
# imported, so a schema change has to be a conscious decision here too.
PROVIDERS = ("openai", "elevenlabs", "gemini", "gemini_multi", "edge")

# The two spellings the stored config uses for the same thing: plain names for
# OpenAI/Edge, opaque ids for ElevenLabs.
_VOICE_KEYS = (("voice_1", "voice_2"), ("voice_1_id", "voice_2_id"))
_NAMED_KEYS = frozenset(
    {"voice_1", "voice_2", "voice_1_id", "voice_2_id", "model", "language_code"}
)


class TTSError(EngineError):
    """Speech synthesis could not be performed (bad config, unknown provider)."""


class TTSProviderError(TTSError):
    """The TTS provider call itself failed — auth, rate limit, timeout, 5xx.

    Same reasoning as ``ProviderError`` in ``llm.py``: the caller's response
    differs by kind, and #543 should not have to import four vendor SDKs just to
    tell an outage apart from a misconfiguration.
    """


class VoiceConfig(BaseModel):
    """The two voices and model for one episode, from the stored TTS config.

    ``tts_configurations.config`` is a flat per-provider dict validated at write
    time by ``src/schemas/tts_configuration.py`` — ``voice_1``/``voice_2`` for
    OpenAI and Edge, ``voice_1_id``/``voice_2_id`` for ElevenLabs, ``model`` plus
    ``language_code`` for the Google pair. This normalises those spellings once
    so no backend has to guess which key its provider used.

    Note what is *not* here: podcastfy's nested
    ``text_to_speech.<provider>.default_voices.{question,answer}`` shape. That
    nesting exists only because podcastfy reads it, and the translation shim at
    ``src/routers/generation.py:58`` exists only to produce it. Both can go at
    the #543 cut-over.
    """

    model_config = ConfigDict(extra="ignore")

    host_voice: str
    guest_voice: str
    model: Optional[str] = None
    language_code: str = "en-US"
    # Provider-specific extras kept verbatim: speed (openai), stability and
    # similarity_boost (elevenlabs), rate and volume (edge).
    options: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_tts_config(
        cls, config: Optional[Dict[str, Any]]
    ) -> "VoiceConfig":
        """Build from the raw ``tts_configurations.config`` JSONB.

        Accepts either voice-key spelling. Raises ``TTSError`` rather than a
        Pydantic error when a voice is missing, because the caller is a Celery
        task that needs to tell "this episode is misconfigured" apart from "this
        code is wrong".
        """
        raw = {k: v for k, v in (config or {}).items() if v is not None}

        host = guest = None
        for host_key, guest_key in _VOICE_KEYS:
            if raw.get(host_key) or raw.get(guest_key):
                host, guest = raw.get(host_key), raw.get(guest_key)
                break

        if not host or not guest:
            raise TTSError(
                "TTS config is missing a voice for both speakers; expected "
                "voice_1/voice_2 or voice_1_id/voice_2_id, got "
                f"{sorted(raw)}"
            )

        return cls(
            host_voice=host,
            guest_voice=guest,
            model=raw.get("model"),
            language_code=raw.get("language_code", "en-US"),
            options={k: v for k, v in raw.items() if k not in _NAMED_KEYS},
        )

    def voice_for(self, speaker: str) -> str:
        """The voice id/name this speaker is read in."""
        return self.host_voice if speaker == "host" else self.guest_voice


class TTSBackend(Protocol):
    """One provider's synthesis strategy.

    ``workdir`` is supplied by the caller — the generation task already creates
    a per-run temp dir it cleans up on every exit path. A backend writes every
    intermediate there and nowhere else, which is the single invariant that
    makes the podcastfy temp-file defects unrepeatable.
    """

    def synthesise(
        self, script: Script, voices: VoiceConfig, workdir: Path
    ) -> Path:
        """Render ``script`` to one MP3 under ``workdir`` and return its path."""
        ...


def turns_for_synthesis(script: Script) -> List[tuple]:
    """``(index, speaker, text)`` for every turn with speakable content.

    Empty turns are dropped rather than sent: every provider bills per request,
    and an empty one buys silence. ``_validate`` in ``script.py`` already
    rejects a script containing them, so this is belt and braces for scripts
    that reach TTS by another route.
    """
    return [
        (index, turn.speaker, turn.text.strip())
        for index, turn in enumerate(script.turns)
        if turn.text and turn.text.strip()
    ]
