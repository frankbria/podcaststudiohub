"""generate_podcast_task on the in-repo engine (issue #543, PR A).

The engine's own layers are tested in test_engine_script / test_engine_tts /
test_engine_transcript against faked SDKs. Here the engine entry points are
faked with ``create_autospec`` against the *real* functions, so a call the
real signature would reject fails the test, and podcastfy is mocked so any
call into it is visible. ``_load_native_inputs`` (the episode-row read) is
faked here and tested against the real database in test_native_inputs.py.
"""
import types
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, create_autospec, patch
from uuid import uuid4

import pytest

from src.config import settings
from src.engine import generate_script as real_generate_script
from src.engine.models import Script
from src.engine.transcript import persist_transcript as real_persist_transcript
from src.engine.tts import synthesise as real_synthesise
from src.tasks.podcast_generation import generate_podcast_task
from tests.module_patching import patch_modules

SCRIPT = Script(
    title="Grounding",
    summary="Two hosts on retrieval.",
    turns=[
        {"speaker": "host", "text": "Welcome back."},
        {"speaker": "guest", "text": "Glad to be here."},
    ],
)
OPENAI_CONFIG = {"model": "gpt-4o-mini-tts", "voice_1": "alloy", "voice_2": "echo"}
TRANSCRIPT_KEY = "podcasts/user-u/episode-e.transcript.json"


class Harness:
    """Fakes for every boundary the native branch crosses, plus a podcastfy spy."""

    def __init__(self):
        self.user_id = str(uuid4())
        # What _load_native_inputs reads from the episode row.
        self.tts_provider = "openai"
        self.tts_config: dict = dict(OPENAI_CONFIG)
        self.generate_script = create_autospec(real_generate_script, return_value=SCRIPT)
        self.synthesise = create_autospec(real_synthesise, side_effect=self._write_audio)
        self.persist_transcript = create_autospec(
            real_persist_transcript, return_value=TRANSCRIPT_KEY
        )
        self.fetch_url_text = MagicMock(return_value="Fetched page text.")
        self.podcastfy = MagicMock()
        self.progress: list[dict[str, Any]] = []

    @staticmethod
    def _write_audio(provider, script, config, workdir):
        out = Path(workdir) / "native.mp3"
        out.write_bytes(b"ID3")
        return out

    def run(self, **kwargs: Any) -> dict[str, Any]:
        podcastfy_module = types.ModuleType("podcastfy")
        podcastfy_module.client = self.podcastfy
        audio = MagicMock()
        audio.__len__ = MagicMock(return_value=60000)
        kwargs.setdefault("episode_id", str(uuid4()))
        with patch.object(
            generate_podcast_task, "update_state",
            side_effect=lambda **kw: self.progress.append(kw.get("meta", {})),
        ), patch_modules(
            {"podcastfy": podcastfy_module, "podcastfy.client": self.podcastfy}
        ), patch(
            "src.tasks.podcast_generation.generate_script", self.generate_script
        ), patch(
            "src.tasks.podcast_generation.synthesise", self.synthesise
        ), patch(
            "src.tasks.podcast_generation.persist_transcript", self.persist_transcript
        ), patch(
            "src.tasks.podcast_generation.ContentExtractionService"
        ) as service, patch(
            "src.tasks.podcast_generation._load_native_inputs",
            return_value=(self.user_id, self.tts_provider, self.tts_config),
        ), patch(
            "src.tasks.podcast_generation.os.path.getsize", return_value=1024
        ), patch(
            "src.tasks.podcast_generation.AudioSegment"
        ) as audio_segment, patch(
            "src.tasks.podcast_generation.finalize_episode_generation_task"
        ):
            service.return_value.fetch_url_text = self.fetch_url_text
            audio_segment.from_file.return_value = audio
            return generate_podcast_task.run(**kwargs)


@pytest.fixture
def harness():
    return Harness()


def test_native_is_the_default_engine():
    assert settings.ENGINE == "native"


def test_native_path_runs_the_engine_end_to_end(harness):
    episode_id = str(uuid4())
    template = {"word_count": 600, "conversation_style": ["engaging"]}

    result = harness.run(
        episode_id=episode_id,
        urls=["https://example.com/post"],
        text_content="Pasted notes.",
        conversation_config=template,
        longform=True,
    )

    harness.podcastfy.generate_podcast.assert_not_called()
    # Pending URL sources are fetched through the SSRF-guarded service (#543).
    harness.fetch_url_text.assert_called_once_with("https://example.com/post")
    call = harness.generate_script.call_args
    assert call.args[0] == ["Pasted notes.", "Fetched page text."]
    assert call.args[1] == template
    assert call.kwargs["longform"] is True
    provider, script, config, workdir = harness.synthesise.call_args.args
    assert (provider, script, config) == ("openai", SCRIPT, OPENAI_CONFIG)
    assert Path(result["audio_file_path"]).parent == Path(workdir)
    harness.persist_transcript.assert_called_once_with(
        SCRIPT, harness.user_id, episode_id
    )
    assert result["status"] == "success"
    assert result["transcript_path"] == TRANSCRIPT_KEY


def test_the_stored_gemini_multi_name_reaches_the_engine_unrenamed(harness):
    """The router renames it to podcastfy's "geminimulti"; the engine must not see that."""
    harness.tts_provider = "gemini_multi"
    harness.tts_config = {"model": "gemini-2.5-flash-tts", "language_code": "en-US"}

    harness.run(text_content="Notes.", tts_model="geminimulti")

    assert harness.synthesise.call_args.args[0] == "gemini_multi"


def test_a_broken_voice_config_fails_before_any_paid_call(harness):
    """Resolving the voices first means a misconfigured episode costs nothing."""
    harness.tts_config = {"model": "x"}

    with pytest.raises(Exception):
        harness.run(text_content="Notes.")

    harness.generate_script.assert_not_called()
    harness.synthesise.assert_not_called()


@pytest.mark.parametrize("kwargs", [
    {"image_paths": ["/tmp/a.png"]},
    {"topic": "AI safety"},
])
def test_unsupported_inputs_are_refused_before_any_paid_call(harness, kwargs):
    with pytest.raises(Exception):
        harness.run(text_content="Notes.", **kwargs)

    harness.generate_script.assert_not_called()


def test_elevenlabs_is_available_on_the_native_path(harness):
    """The #542 fail-fast guard is about podcastfy's broken ElevenLabs call only."""
    harness.tts_provider = "elevenlabs"
    harness.tts_config = {"model": "eleven_v3", "voice_1_id": "a", "voice_2_id": "b"}

    result = harness.run(text_content="Notes.", tts_model="elevenlabs")

    assert result["status"] == "success"
    assert harness.synthesise.call_args.args[0] == "elevenlabs"


def test_script_progress_is_reported_between_33_and_66(harness):
    def generate(sources, config, longform=False, on_progress=None):
        on_progress("scripting", 50)
        on_progress("scripting", 100)
        return SCRIPT

    harness.generate_script.side_effect = generate

    harness.run(text_content="Notes.")

    transcript = [
        m["progress"] for m in harness.progress if m.get("stage") == "transcript"
    ]
    # A real mid-script value, not just the fixed 33/66 markers podcastfy gave.
    assert any(33 < p < 66 for p in transcript) and 66 in transcript
    assert all(33 <= p <= 66 for p in transcript)


def test_engine_podcastfy_is_the_rollback_switch(harness, monkeypatch):
    monkeypatch.setattr(settings, "ENGINE", "podcastfy")
    harness.podcastfy.generate_podcast.return_value = "/tmp/rollback.mp3"

    result = harness.run(text_content="Notes.")

    harness.podcastfy.generate_podcast.assert_called_once()
    harness.generate_script.assert_not_called()
    assert result["transcript_path"] is None  # podcastfy discards its transcript


def test_the_elevenlabs_guard_still_protects_the_podcastfy_path(harness, monkeypatch):
    monkeypatch.setattr(settings, "ENGINE", "podcastfy")

    with pytest.raises(Exception):
        harness.run(text_content="Notes.", tts_model="elevenlabs")

    harness.podcastfy.generate_podcast.assert_not_called()
