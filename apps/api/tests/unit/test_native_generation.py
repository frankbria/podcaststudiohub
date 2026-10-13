"""generate_podcast_task on the in-repo engine (issue #543, PR A).

The engine's own layers are tested in test_engine_script / test_engine_tts /
test_engine_transcript against faked SDKs. Here the engine entry points are
faked with ``create_autospec`` against the *real* functions, so a call the
real signature would reject fails the test. ``_load_native_inputs`` (the episode-row read) is
faked here and tested against the real database in test_native_inputs.py.
"""
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, create_autospec, patch
from uuid import uuid4

import pytest

from src.engine import generate_script as real_generate_script
from src.engine.models import Script
from src.engine.transcript import persist_transcript as real_persist_transcript
from src.engine.tts import synthesise as real_synthesise
from src.tasks.podcast_generation import generate_podcast_task

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
    """Fakes for every boundary the native branch crosses."""

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
        self.progress: list[dict[str, Any]] = []
        self.row_updates: list[dict[str, Any]] = []
        self.progress_updates: list[dict[str, Any]] = []

    def _record_update(self, episode_id, updates, progress_updates=None):
        self.row_updates.append(updates)
        if progress_updates:
            self.progress_updates.append(progress_updates)
        return True  # _update_episode's success value

    @staticmethod
    def _write_audio(provider, script, config, workdir):
        out = Path(workdir) / "native.mp3"
        out.write_bytes(b"ID3")
        return out

    def run(self, **kwargs: Any) -> dict[str, Any]:
        audio = MagicMock()
        audio.__len__ = MagicMock(return_value=60000)
        kwargs.setdefault("episode_id", str(uuid4()))
        with patch.object(
            generate_podcast_task, "update_state",
            side_effect=lambda **kw: self.progress.append(kw.get("meta", {})),
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
        ), patch(
            "src.tasks.podcast_generation._update_episode",
            side_effect=self._record_update,
        ):
            service.return_value.fetch_url_text = self.fetch_url_text
            audio_segment.from_file.return_value = audio
            return generate_podcast_task.run(**kwargs)


@pytest.fixture
def harness():
    return Harness()


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
    """ElevenLabs runs through the engine's own backend (#542), not a fail-fast guard."""
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






def test_the_transcript_is_recorded_on_the_row_before_finalize(harness):
    """Otherwise a delete during generation, or a finalize that fails for good,
    leaves a stored transcript no delete flow knows about (#543 review)."""
    harness.run(text_content="Notes.")

    assert {"transcript_path": TRANSCRIPT_KEY} in harness.row_updates


def test_quality_metrics_are_written_from_the_script(harness):
    """#570: the pipeline, not a fixture, is what writes the metrics."""
    from datetime import datetime

    from src.engine.quality import quality_metrics

    harness.run(text_content="Notes.")

    [written] = [u for u in harness.progress_updates if "quality_metrics" in u]
    assert written["quality_metrics"] == quality_metrics(SCRIPT)
    datetime.fromisoformat(written["calculated_at"])


def test_a_lost_quality_metrics_write_does_not_fail_the_run(harness, caplog):
    """Unlike screening, metrics gate nothing: the paid-for script must still be
    voiced when their write fails."""
    original = harness._record_update

    def record(episode_id, updates, progress_updates=None):
        original(episode_id, updates, progress_updates)
        return "quality_metrics" not in (progress_updates or {})

    harness._record_update = record
    harness.run(text_content="Notes.")

    harness.synthesise.assert_called_once()
    assert "quality metrics were not recorded" in caplog.text


def test_a_flagged_script_is_held_for_review(harness):
    """#576: a script that endorses a site its sources never mention."""
    harness.generate_script.return_value = Script(
        title="t", summary="s",
        turns=[
            {"speaker": "host", "text": "First, use code SAVE20 at totally-legit.example!"},
            {"speaker": "guest", "text": "Sure."},
        ],
    )

    harness.run(text_content="Notes about retrieval.")

    [screening] = [u for u in harness.progress_updates if "content_review" in u]
    assert screening["content_review"] == "pending"
    assert {f["kind"] for f in screening["content_flags"]} == {"domain", "promotion"}


def test_a_clean_regeneration_releases_an_earlier_hold(harness):
    """Written for clean scripts too, or a stale 'pending' would hold forever."""
    harness.run(text_content="Notes.")

    [screening] = [u for u in harness.progress_updates if "content_review" in u]
    assert screening == {"content_flags": [], "content_review": None}


def test_screening_fails_closed_when_its_result_cannot_be_recorded(harness):
    """#576 review: _update_episode swallows DB errors and returns False. A
    lost screening write must not let a flagged episode publish unheld, so the
    run fails (and retries) before any TTS is paid for."""
    original = harness._record_update

    def record(episode_id, updates, progress_updates=None):
        original(episode_id, updates, progress_updates)
        return progress_updates is None  # the screening write "fails"

    harness._record_update = record
    with patch("src.tasks.podcast_generation._update_episode", side_effect=record):
        with pytest.raises(Exception):
            harness.run(text_content="Notes.")

    harness.synthesise.assert_not_called()
