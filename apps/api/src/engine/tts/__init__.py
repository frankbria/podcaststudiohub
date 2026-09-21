"""In-repo TTS layer (epic #538, step 2 — issue #542).

Replaces ``podcastfy.text_to_speech`` and its five providers. One interface,
five backends, every temp file under a caller-supplied ``workdir``, no
module-global API keys, and Eleven v3 Text-to-Dialogue — which podcastfy's
pinned SDK could not reach at all.

The live ``generate_podcast_task`` does not call this yet; #543 cuts over.
"""
from src.engine.tts.base import (
    PROVIDERS,
    TTSBackend,
    TTSError,
    TTSProviderError,
    VoiceConfig,
)
from src.engine.tts.factory import get_backend

__all__ = [
    "PROVIDERS",
    "TTSBackend",
    "TTSError",
    "TTSProviderError",
    "VoiceConfig",
    "get_backend",
    "synthesise",
]


def synthesise(provider, script, config, workdir):
    """Render ``script`` to one MP3 using the configured provider.

    The single entry point #543 will call: provider string and raw
    ``tts_configurations.config`` in, finished audio path out.
    """
    return get_backend(provider).synthesise(
        script, VoiceConfig.from_tts_config(config), workdir
    )
