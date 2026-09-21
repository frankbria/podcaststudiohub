"""Google Cloud TTS backends (issue #542) — single- and multi-speaker.

The multi-speaker one is not a port. podcastfy pinned the literal
``en-US-Studio-MultiSpeaker`` in three places and its ``validate_parameters``
actively *rejected* any other model (`tts/providers/geminimulti.py:335`), so the
model was not merely a default — it was enforced. That Studio voice is now
restricted, and Google's supported path is Gemini-TTS, which takes a different
request shape: speakers are declared up front as aliases in a
``MultiSpeakerVoiceConfig`` and the markup turns reference those aliases, rather
than carrying bare voice letters like "R" and "S".

Model ids come from settings and were read off Google's current Text-to-Speech
docs (`cloud.google.com/text-to-speech/docs/gemini-tts`) on 2026-09-21. As with
the LLM model ids in `config.py`, no test can catch a wrong one — the SDK is
faked at the boundary — so changing them needs a live smoke test.
"""
import logging
from pathlib import Path

from google.api_core import exceptions as google_exceptions
from google.cloud import texttospeech

from src.config import settings
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

# Aliases the markup uses to point at the two configured voices. Arbitrary but
# stable; only their pairing with speaker_id matters to the API.
_HOST_ALIAS = "Host"
_GUEST_ALIAS = "Guest"


def _is_gemini_tts_model(value) -> bool:
    """Gemini-TTS model ids look like ``gemini-2.5-flash-tts``.

    The app's config writer still stores `en-US-Studio-MultiSpeaker` in the
    `model` field, which is a *voice* name, not a model id.
    """
    return bool(value) and str(value).startswith("gemini-")


def _gemini_tts_model(stored) -> str:
    """The multi-speaker model to send, ignoring a stored voice name.

    `model` is required at write time, so a plain ``stored or default`` would
    never fall back -- and the stored value is the restricted Studio voice for
    every row the app has written, which is not a model at all.
    """
    if _is_gemini_tts_model(stored):
        return stored
    if stored:
        logger.warning(
            "Stored Gemini model %r is not a Gemini-TTS model id; using %s",
            stored, settings.ENGINE_GEMINI_TTS_MODEL,
        )
    return settings.ENGINE_GEMINI_TTS_MODEL


class GeminiTTS:
    """Single-speaker synthesis, one request per turn."""

    def synthesise(
        self, script: Script, voices: VoiceConfig, workdir: Path
    ) -> Path:
        turns = turns_for_synthesis(script)
        if not turns:
            raise TTSError("Script has no speakable turns")

        client = texttospeech.TextToSpeechClient()
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3
        )

        def render(turn) -> bytes:
            _, speaker, text = turn
            # model_name is sent only when the stored value is a Gemini-TTS
            # model id. Classic prebuilt voices take no model, and the app
            # still stores a Studio *voice name* in that field, which the API
            # would reject as a model.
            params = {
                "language_code": voices.language_code,
                "name": voices.voice_for(speaker),
            }
            if _is_gemini_tts_model(voices.model):
                params["model_name"] = voices.model
            voice_params = texttospeech.VoiceSelectionParams(**params)
            try:
                response = client.synthesize_speech(
                    input=texttospeech.SynthesisInput(text=text),
                    voice=voice_params,
                    audio_config=audio_config,
                )
            except google_exceptions.GoogleAPIError as exc:
                raise TTSProviderError(f"Gemini TTS call failed: {exc}") from exc
            return response.audio_content

        segments = synthesise_concurrently(render, turns)
        return concat_to_mp3(segments, workdir, "episode.mp3")


class GeminiMultiTTS:
    """Multi-speaker synthesis: the whole conversation in one request."""

    def synthesise(
        self, script: Script, voices: VoiceConfig, workdir: Path
    ) -> Path:
        turns = turns_for_synthesis(script)
        if not turns:
            raise TTSError("Script has no speakable turns")

        client = texttospeech.TextToSpeechClient()
        model = _gemini_tts_model(voices.model)

        markup = texttospeech.MultiSpeakerMarkup(
            turns=[
                texttospeech.MultiSpeakerMarkup.Turn(
                    text=text,
                    speaker=_HOST_ALIAS if speaker == "host" else _GUEST_ALIAS,
                )
                for _, speaker, text in turns
            ]
        )
        voice_params = texttospeech.VoiceSelectionParams(
            language_code=voices.language_code,
            model_name=model,
            multi_speaker_voice_config=texttospeech.MultiSpeakerVoiceConfig(
                speaker_voice_configs=[
                    texttospeech.MultispeakerPrebuiltVoice(
                        speaker_alias=_HOST_ALIAS,
                        speaker_id=voices.host_voice,
                    ),
                    texttospeech.MultispeakerPrebuiltVoice(
                        speaker_alias=_GUEST_ALIAS,
                        speaker_id=voices.guest_voice,
                    ),
                ]
            ),
        )

        try:
            response = client.synthesize_speech(
                input=texttospeech.SynthesisInput(multi_speaker_markup=markup),
                voice=voice_params,
                audio_config=texttospeech.AudioConfig(
                    audio_encoding=texttospeech.AudioEncoding.MP3
                ),
            )
        except google_exceptions.GoogleAPIError as exc:
            raise TTSProviderError(
                f"Gemini multi-speaker TTS call failed: {exc}"
            ) from exc

        return concat_to_mp3([response.audio_content], workdir, "episode.mp3")
