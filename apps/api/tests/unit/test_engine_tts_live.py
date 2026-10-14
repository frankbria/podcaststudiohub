"""Opt-in live TTS tests: each calls a real provider and spends its credits.

They are separate from `test_engine_tts.py` because that module's autouse
fixtures replace the provider keys and pydub, so a live test there fails with
401 or produces a nine-byte "mp3" whatever key is configured (#617).

Gated on an explicit flag, NOT on the key being set. CI has no provider
secrets, and a key in .env can be present, well-formed and revoked (all of them
were until 2026-10-11), so a key-presence gate would turn a stale .env into red
tests rather than skipped ones.

    RUN_LIVE_TTS_TESTS=1 uv run pytest tests/unit/test_engine_tts_live.py --no-cov

Needs ffmpeg, the provider key where `src.config` reads it (`apps/api/.env` or
the environment), and, only because `tests/conftest.py` is imported, the
migrated test Postgres and Redis.
"""

import os

import pytest

from src.config import settings
from src.engine.tts import synthesise
from tests.unit.test_engine_tts import EDGE_CONFIG, ELEVEN_CONFIG, SCRIPT

pytestmark = [
    pytest.mark.live_tts,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_TTS_TESTS") != "1",
        reason="opt-in: set RUN_LIVE_TTS_TESTS=1 and supply a working provider key",
    ),
]


def test_live_elevenlabs_dialogue(tmp_path):
    # ELEVEN_CONFIG's voiceA/voiceB are the fakes' placeholders; the real API
    # rejects them before Text-to-Dialogue runs. Any two of the account's
    # voices will do, and a key scoped to TTS + voices_read can list them.
    import httpx
    from elevenlabs.client import ElevenLabs

    # Its own httpx client, closed here: the SDK client has no close() (#653).
    with httpx.Client() as http:
        account = ElevenLabs(api_key=settings.ELEVENLABS_API_KEY, httpx_client=http)
        voices = account.voices.search(page_size=2).voices
    assert len(voices) == 2, "the ElevenLabs account needs at least two voices"
    config = {**ELEVEN_CONFIG, "voice_1_id": voices[0].voice_id, "voice_2_id": voices[1].voice_id}

    output = synthesise("elevenlabs", SCRIPT, config, tmp_path)

    assert output.is_file()
    assert output.stat().st_size > 10_000, "suspiciously small for four turns"


def test_live_edge(tmp_path):
    """Needs no API key at all, so this is the cheapest end-to-end check."""
    output = synthesise("edge", SCRIPT, EDGE_CONFIG, tmp_path)

    assert output.is_file()
    assert output.stat().st_size > 10_000
