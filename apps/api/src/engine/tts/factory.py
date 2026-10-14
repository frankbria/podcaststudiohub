"""Provider dispatch for the TTS layer (issue #542).

Flat ``if provider == ...`` rather than a registry dict, matching
``src/engine/llm.py``. podcastfy used a registry (`tts/factory.py`) whose
constructor call was positional-by-convention — `provider_class(api_key, model)`
— which only worked because all five providers happened to share an argument
order. Five explicit branches cannot develop that kind of coupling.

The provider strings are exactly the five ``tts_configurations.provider`` is
constrained to, including ``gemini_multi`` with the underscore. podcastfy
spelled it without one, which was the entire reason for the router's rename
shim (removed in #623); nothing here needs it.
"""
from src.engine.tts.base import TTSBackend, TTSError


def get_backend(provider: str) -> TTSBackend:
    """The backend for a stored ``tts_configurations.provider`` value."""
    if provider == "openai":
        from src.engine.tts.openai import OpenAITTS

        return OpenAITTS()
    if provider == "elevenlabs":
        from src.engine.tts.elevenlabs import ElevenLabsTTS

        return ElevenLabsTTS()
    if provider == "gemini":
        from src.engine.tts.gemini import GeminiTTS

        return GeminiTTS()
    if provider == "gemini_multi":
        from src.engine.tts.gemini import GeminiMultiTTS

        return GeminiMultiTTS()
    if provider == "edge":
        from src.engine.tts.edge import EdgeTTS

        return EdgeTTS()
    raise TTSError(
        f"Unsupported TTS provider {provider!r}; expected one of "
        "openai, elevenlabs, gemini, gemini_multi, edge"
    )
