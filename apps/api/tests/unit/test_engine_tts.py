"""Unit tests for the in-repo TTS layer (issue #542).

Provider SDKs are faked at the boundary with ``create_autospec`` against the
*real installed* method, the repo's drift guard: a call with a kwarg the vendor
does not accept fails here instead of in production.

pydub is patched rather than exercised. CI has no ffmpeg — `pytest.ini` already
carries the matching pydub warning filter — so real decoding would make these
tests pass locally and fail in CI, or vice versa.

No test here makes a network call. The opt-in live tests live at the bottom and
skip unless RUN_LIVE_TTS_TESTS=1.
"""
import os
from pathlib import Path
from unittest.mock import MagicMock, create_autospec, patch

import pytest

from src.config import settings
from src.engine.models import Script
from src.engine.tts import PROVIDERS, TTSError, VoiceConfig, get_backend, synthesise
from src.engine.tts.base import TTSProviderError, turns_for_synthesis
from src.engine.tts.elevenlabs import batch_turns

SCRIPT = Script(
    title="What Retrieval-Augmented Generation Actually Fixes",
    summary="Two hosts discuss grounding a model in fetched documents.",
    turns=[
        {"speaker": "host", "text": "Welcome to The Signal Room."},
        {"speaker": "guest", "text": "Glad to be here. Let's get into it."},
        {"speaker": "host", "text": "So what does retrieval actually buy you?"},
        {"speaker": "guest", "text": "Inspectable failures, mostly."},
    ],
)

OPENAI_CONFIG = {"model": "gpt-4o-mini-tts", "voice_1": "alloy", "voice_2": "echo"}
ELEVEN_CONFIG = {"model": "eleven_v3", "voice_1_id": "voiceA", "voice_2_id": "voiceB"}
GEMINI_CONFIG = {"model": "gemini-2.5-flash-tts", "language_code": "en-US",
                 "voice_1": "Kore", "voice_2": "Charon"}
EDGE_CONFIG = {"voice_1": "en-US-AriaNeural", "voice_2": "en-US-GuyNeural"}

MP3 = b"ID3fake-mp3-bytes"


@pytest.fixture
def workdir(tmp_path) -> Path:
    return tmp_path / "run"


@pytest.fixture(autouse=True)
def _fake_pydub():
    """Patch pydub so no test needs ffmpeg, and record what was exported."""
    segment = MagicMock()
    segment.__iadd__ = lambda self, other: self
    segment.__add__ = lambda self, other: self

    with patch("pydub.AudioSegment") as audio_segment:
        audio_segment.empty.return_value = segment
        audio_segment.from_file.return_value = segment

        def _export(path, **kwargs):
            Path(path).write_bytes(b"final-mp3")
            return MagicMock()

        segment.export.side_effect = _export
        yield audio_segment


@pytest.fixture(autouse=True)
def _keys():
    with patch.object(settings, "OPENAI_API_KEY", "test-openai"), patch.object(
        settings, "ELEVENLABS_API_KEY", "test-eleven"
    ):
        yield


# --------------------------------------------------------------------------
# VoiceConfig — maps the stored tts_configurations.config JSONB
# --------------------------------------------------------------------------

def test_voice_config_accepts_the_plain_name_spelling():
    voices = VoiceConfig.from_tts_config({**OPENAI_CONFIG, "speed": 1.1})

    assert voices.host_voice == "alloy"
    assert voices.guest_voice == "echo"
    assert voices.model == "gpt-4o-mini-tts"
    assert voices.options == {"speed": 1.1}


def test_voice_config_accepts_the_voice_id_spelling():
    """ElevenLabs stores opaque ids under different keys than OpenAI's names."""
    voices = VoiceConfig.from_tts_config({**ELEVEN_CONFIG, "stability": 0.5})

    assert voices.host_voice == "voiceA"
    assert voices.guest_voice == "voiceB"
    assert voices.options == {"stability": 0.5}


def test_voice_config_maps_speakers_to_the_right_voice():
    voices = VoiceConfig.from_tts_config(OPENAI_CONFIG)

    assert voices.voice_for("host") == "alloy"
    assert voices.voice_for("guest") == "echo"


@pytest.mark.parametrize(
    "config",
    [None, {}, {"model": "x"}, {"voice_1": "alloy"}, {"voice_1_id": "a"}],
    ids=["none", "empty", "model-only", "one-name", "one-id"],
)
def test_voice_config_rejects_a_config_missing_a_speaker(config):
    """A half-configured episode must fail as configuration, not as a
    Pydantic error the Celery task cannot classify."""
    with pytest.raises(TTSError, match="missing a voice"):
        VoiceConfig.from_tts_config(config, "openai")


def test_empty_turns_are_never_sent_to_a_provider():
    """Every provider bills per request; an empty one buys silence."""
    script = Script(
        title="t",
        summary="s",
        turns=[
            {"speaker": "host", "text": "Real content."},
            {"speaker": "guest", "text": "   "},
            {"speaker": "host", "text": ""},
        ],
    )

    assert [t[2] for t in turns_for_synthesis(script)] == ["Real content."]


# --------------------------------------------------------------------------
# Factory
# --------------------------------------------------------------------------

def test_every_stored_provider_value_resolves_to_a_backend():
    """These five strings are what the schema constrains the column to; a
    provider that does not resolve is an episode that cannot generate."""
    for provider in PROVIDERS:
        assert hasattr(get_backend(provider), "synthesise")


def test_gemini_multi_keeps_its_underscore():
    """podcastfy registered it as 'geminimulti', which is the only reason the
    rename shim in routers/generation.py exists. Nothing here needs it."""
    from src.engine.tts.gemini import GeminiMultiTTS

    assert isinstance(get_backend("gemini_multi"), GeminiMultiTTS)


def test_unknown_provider_raises():
    with pytest.raises(TTSError, match="Unsupported TTS provider"):
        get_backend("festival")


# --------------------------------------------------------------------------
# OpenAI backend
# --------------------------------------------------------------------------

def _real_openai_speech_create():
    import openai

    return openai.OpenAI(api_key="test").audio.speech.create


def fake_openai_client(count: int = 8):
    client = MagicMock()
    client.audio.speech.create = create_autospec(
        _real_openai_speech_create(),
        side_effect=[MagicMock(content=MP3) for _ in range(count)],
    )
    return client


def test_openai_synthesises_every_turn_and_returns_one_file(workdir):
    client = fake_openai_client()

    with patch("src.engine.tts.openai.openai.OpenAI", return_value=client):
        output = synthesise("openai", SCRIPT, OPENAI_CONFIG, workdir)

    assert client.audio.speech.create.call_count == len(SCRIPT.turns)
    assert output.parent == workdir
    assert output.is_file()


def test_openai_never_sets_the_module_global_api_key(workdir):
    """podcastfy did `openai.api_key = api_key` (tts/providers/openai.py:22),
    which is process-wide state that clobbers any other key in the worker and
    forecloses bring-your-own-key."""
    import openai as openai_sdk

    before = openai_sdk.api_key

    with patch("src.engine.tts.openai.openai.OpenAI", return_value=fake_openai_client()):
        synthesise("openai", SCRIPT, OPENAI_CONFIG, workdir)

    assert openai_sdk.api_key is before


def test_openai_uses_the_configured_voice_per_speaker(workdir):
    client = fake_openai_client()

    with patch("src.engine.tts.openai.openai.OpenAI", return_value=client):
        synthesise("openai", SCRIPT, OPENAI_CONFIG, workdir)

    voices = [c.kwargs["voice"] for c in client.audio.speech.create.call_args_list]
    assert voices == ["alloy", "echo", "alloy", "echo"]


def test_openai_missing_key_raises_before_any_call(workdir):
    client = fake_openai_client()

    with patch.object(settings, "OPENAI_API_KEY", None), patch(
        "src.engine.tts.openai.openai.OpenAI", return_value=client
    ):
        with pytest.raises(TTSError, match="OPENAI_API_KEY"):
            synthesise("openai", SCRIPT, OPENAI_CONFIG, workdir)

    assert client.audio.speech.create.call_count == 0


def test_openai_api_error_becomes_a_provider_error(workdir):
    import openai as openai_sdk

    client = MagicMock()
    client.audio.speech.create = create_autospec(
        _real_openai_speech_create(),
        side_effect=openai_sdk.APIConnectionError(request=MagicMock()),
    )

    with patch("src.engine.tts.openai.openai.OpenAI", return_value=client):
        with pytest.raises(TTSProviderError, match="OpenAI TTS call failed"):
            synthesise("openai", SCRIPT, OPENAI_CONFIG, workdir)


def test_turn_order_survives_concurrent_synthesis(workdir, _fake_pydub):
    """Concurrency is the whole point of the rewrite, and turn order is the one
    thing it must not disturb — a raced episode is unlistenable."""
    client = MagicMock()
    per_turn = [b"A", b"B", b"C", b"D"]
    client.audio.speech.create = create_autospec(
        _real_openai_speech_create(),
        side_effect=[MagicMock(content=blob) for blob in per_turn],
    )

    with patch.object(settings, "ENGINE_TTS_MAX_CONCURRENCY", 4), patch(
        "src.engine.tts.openai.openai.OpenAI", return_value=client
    ):
        synthesise("openai", SCRIPT, OPENAI_CONFIG, workdir)

    decoded = [c.args[0].read() for c in _fake_pydub.from_file.call_args_list]
    assert decoded == per_turn


def test_concurrency_is_bounded_by_the_setting(workdir):
    client = fake_openai_client()

    with patch.object(settings, "ENGINE_TTS_MAX_CONCURRENCY", 2), patch(
        "src.engine.tts.openai.ThreadPoolExecutor"
    ) as pool, patch("src.engine.tts.openai.openai.OpenAI", return_value=client):
        pool.return_value.__enter__.return_value.map.return_value = [MP3] * 4
        synthesise("openai", SCRIPT, OPENAI_CONFIG, workdir)

    assert pool.call_args.kwargs["max_workers"] == 2


# --------------------------------------------------------------------------
# ElevenLabs backend — Text-to-Dialogue
# --------------------------------------------------------------------------

def _real_dialogue_convert():
    from elevenlabs.client import ElevenLabs

    return ElevenLabs(api_key="test").text_to_dialogue.convert


def fake_eleven_client(batches: int = 1):
    client = MagicMock()
    client.text_to_dialogue.convert = create_autospec(
        _real_dialogue_convert(), side_effect=[iter([MP3]) for _ in range(batches)]
    )
    return client


def test_elevenlabs_sends_the_whole_conversation_in_one_dialogue_request(workdir):
    """The capability podcastfy could not reach: turns rendered together, so the
    model can time reactions, rather than one isolated call per turn."""
    client = fake_eleven_client()

    with patch("src.engine.tts.elevenlabs.ElevenLabs", return_value=client):
        synthesise("elevenlabs", SCRIPT, ELEVEN_CONFIG, workdir)

    assert client.text_to_dialogue.convert.call_count == 1
    kwargs = client.text_to_dialogue.convert.call_args.kwargs
    assert len(kwargs["inputs"]) == len(SCRIPT.turns)
    assert kwargs["model_id"] == "eleven_v3"


def test_elevenlabs_pairs_each_turn_with_its_speaker_voice(workdir):
    client = fake_eleven_client()

    with patch("src.engine.tts.elevenlabs.ElevenLabs", return_value=client):
        synthesise("elevenlabs", SCRIPT, ELEVEN_CONFIG, workdir)

    inputs = client.text_to_dialogue.convert.call_args.kwargs["inputs"]
    assert [i.voice_id for i in inputs] == ["voiceA", "voiceB", "voiceA", "voiceB"]
    assert inputs[0].text == "Welcome to The Signal Room."


def test_elevenlabs_missing_key_raises(workdir):
    with patch.object(settings, "ELEVENLABS_API_KEY", None):
        with pytest.raises(TTSError, match="ELEVENLABS_API_KEY"):
            synthesise("elevenlabs", SCRIPT, ELEVEN_CONFIG, workdir)


def test_elevenlabs_error_becomes_a_provider_error(workdir):
    client = MagicMock()
    client.text_to_dialogue.convert = create_autospec(
        _real_dialogue_convert(), side_effect=RuntimeError("429 too many requests")
    )

    with patch("src.engine.tts.elevenlabs.ElevenLabs", return_value=client):
        with pytest.raises(TTSProviderError, match="Text-to-Dialogue call failed"):
            synthesise("elevenlabs", SCRIPT, ELEVEN_CONFIG, workdir)


# --- the character cap ---

def _turns(*lengths):
    return [(i, "host" if i % 2 == 0 else "guest", "x" * n)
            for i, n in enumerate(lengths)]


def test_batching_keeps_each_request_under_the_character_cap():
    """The cap is the total across every input in one request. Exceeding it
    returns a validation error, or truncates a streaming response part-way."""
    batches = batch_turns(_turns(800, 800, 800, 800), char_limit=2000)

    assert len(batches) == 2
    for batch in batches:
        assert sum(len(t[2]) for t in batch) <= 2000


def test_batching_keeps_turns_together_while_they_fit():
    """Bigger batches sound better — the model only times reactions across turns
    it sees together — so the cap is the only reason to ever split."""
    batches = batch_turns(_turns(100, 100, 100), char_limit=2000)

    assert len(batches) == 1


def test_batching_preserves_turn_order_across_batches():
    batches = batch_turns(_turns(1500, 1500, 1500), char_limit=2000)
    flattened = [t[0] for batch in batches for t in batch]

    assert flattened == [0, 1, 2]


def test_a_single_turn_over_the_cap_is_sent_alone_not_split():
    """Splitting mid-sentence would sound worse than a clear provider error."""
    batches = batch_turns(_turns(5000), char_limit=2000)

    assert len(batches) == 1 and len(batches[0]) == 1


def test_elevenlabs_splits_a_long_script_into_several_requests(workdir):
    long_script = Script(
        title="t",
        summary="s",
        turns=[{"speaker": "host" if i % 2 == 0 else "guest", "text": "y" * 700}
               for i in range(6)],
    )
    client = fake_eleven_client(batches=3)

    with patch("src.engine.tts.elevenlabs.ElevenLabs", return_value=client):
        synthesise("elevenlabs", long_script, ELEVEN_CONFIG, workdir)

    assert client.text_to_dialogue.convert.call_count == 3


def test_audio_tags_reach_the_provider_untouched(workdir):
    """[laughs]-style tags are an Eleven v3 feature; stripping or escaping them
    would silently drop the expressiveness they exist for."""
    tagged = Script(
        title="t", summary="s",
        turns=[
            {"speaker": "host", "text": "[laughs] That's the whole trick."},
            {"speaker": "guest", "text": "[curious] Is it really?"},
        ],
    )
    client = fake_eleven_client()

    with patch("src.engine.tts.elevenlabs.ElevenLabs", return_value=client):
        synthesise("elevenlabs", tagged, ELEVEN_CONFIG, workdir)

    inputs = client.text_to_dialogue.convert.call_args.kwargs["inputs"]
    assert inputs[0].text.startswith("[laughs]")
    assert inputs[1].text.startswith("[curious]")


# --------------------------------------------------------------------------
# Google backends
# --------------------------------------------------------------------------

def fake_google_client(count: int = 8):
    client = MagicMock()
    client.synthesize_speech.side_effect = [
        MagicMock(audio_content=MP3) for _ in range(count)
    ]
    return client


def test_gemini_multi_sends_one_request_with_speaker_aliases(workdir):
    """Gemini-TTS declares speakers up front as aliases and has the markup
    reference them — podcastfy tagged turns with bare voice letters R and S on
    a Studio model it hard-enforced and that is now restricted."""
    client = fake_google_client()

    with patch(
        "src.engine.tts.gemini.texttospeech.TextToSpeechClient", return_value=client
    ):
        synthesise("gemini_multi", SCRIPT, GEMINI_CONFIG, workdir)

    assert client.synthesize_speech.call_count == 1
    kwargs = client.synthesize_speech.call_args.kwargs
    voice = kwargs["voice"]
    assert voice.model_name == "gemini-2.5-flash-tts"
    aliases = [c.speaker_alias for c in voice.multi_speaker_voice_config.speaker_voice_configs]
    ids = [c.speaker_id for c in voice.multi_speaker_voice_config.speaker_voice_configs]
    assert aliases == ["Host", "Guest"]
    assert ids == ["Kore", "Charon"]
    # Every turn is carried in the markup, in order.
    assert [t.text for t in kwargs["input"].multi_speaker_markup.turns] == [
        turn.text for turn in SCRIPT.turns
    ]


def test_gemini_multi_markup_speakers_match_the_declared_aliases(workdir):
    """A turn tagged with an alias that was never declared renders silently in
    the wrong voice."""
    client = fake_google_client()

    with patch(
        "src.engine.tts.gemini.texttospeech.TextToSpeechClient", return_value=client
    ):
        synthesise("gemini_multi", SCRIPT, GEMINI_CONFIG, workdir)

    kwargs = client.synthesize_speech.call_args.kwargs
    declared = {
        c.speaker_alias
        for c in kwargs["voice"].multi_speaker_voice_config.speaker_voice_configs
    }
    used = {t.speaker for t in kwargs["input"].multi_speaker_markup.turns}
    assert used <= declared
    assert used == {"Host", "Guest"}


def test_gemini_single_speaker_synthesises_per_turn(workdir):
    client = fake_google_client()

    with patch(
        "src.engine.tts.gemini.texttospeech.TextToSpeechClient", return_value=client
    ):
        synthesise("gemini", SCRIPT, GEMINI_CONFIG, workdir)

    assert client.synthesize_speech.call_count == len(SCRIPT.turns)
    names = [c.kwargs["voice"].name for c in client.synthesize_speech.call_args_list]
    assert names == ["Kore", "Charon", "Kore", "Charon"]


def test_google_api_error_becomes_a_provider_error(workdir):
    from google.api_core import exceptions as google_exceptions

    client = MagicMock()
    client.synthesize_speech.side_effect = google_exceptions.ServiceUnavailable("down")

    with patch(
        "src.engine.tts.gemini.texttospeech.TextToSpeechClient", return_value=client
    ):
        with pytest.raises(TTSProviderError, match="Gemini"):
            synthesise("gemini_multi", SCRIPT, GEMINI_CONFIG, workdir)


# --------------------------------------------------------------------------
# Edge backend
# --------------------------------------------------------------------------

def test_edge_writes_every_intermediate_inside_the_workdir(workdir):
    """podcastfy's multi-speaker merge wrote temp_chunk_{i}.mp3 into the process
    working directory, which collides under the prefork pool."""
    seen = []

    async def fake_save(text, voice, destination, options):
        seen.append(Path(destination))
        Path(destination).write_bytes(MP3)

    with patch("src.engine.tts.edge._save", side_effect=fake_save):
        output = synthesise("edge", SCRIPT, EDGE_CONFIG, workdir)

    assert seen, "no audio was written"
    for path in seen:
        assert workdir in path.parents
    assert output.parent == workdir


def test_edge_names_intermediates_by_turn_so_they_cannot_collide(workdir):
    seen = []

    async def fake_save(text, voice, destination, options):
        seen.append(Path(destination).name)
        Path(destination).write_bytes(MP3)

    with patch("src.engine.tts.edge._save", side_effect=fake_save):
        synthesise("edge", SCRIPT, EDGE_CONFIG, workdir)

    assert len(set(seen)) == len(seen) == len(SCRIPT.turns)


def test_edge_does_not_patch_the_global_event_loop_policy():
    """podcastfy called nest_asyncio.apply() inside the provider, a process-wide
    side effect imposed by whichever provider happened to be selected.

    Checked over the parsed AST rather than the raw text: this module's
    docstring names both `nest_asyncio` and `get_event_loop` to explain what it
    avoids, and a substring scan would flag that prose as the offence.
    """
    import ast

    tree = ast.parse(Path("src/engine/tts/edge.py").read_text())

    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in getattr(node, "names", [])
        if isinstance(node, ast.Import) or node.module
    }
    assert "nest_asyncio" not in imported, imported

    called = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "get_event_loop" not in called, called
    assert "run" in called, "edge backend should drive its coroutine with asyncio.run"


def test_edge_failure_becomes_a_provider_error(workdir):
    async def boom(text, voice, destination, options):
        raise OSError("websocket closed")

    with patch("src.engine.tts.edge._save", side_effect=boom):
        with pytest.raises(TTSProviderError, match="Edge TTS call failed"):
            synthesise("edge", SCRIPT, EDGE_CONFIG, workdir)


# --------------------------------------------------------------------------
# Audio assembly
# --------------------------------------------------------------------------

def test_audio_is_exported_at_the_repo_bitrate(workdir, _fake_pydub):
    """192k matches audio_composition.py. podcastfy was inconsistent: 320k on
    its multi-speaker path, pydub's default on the per-turn one."""
    with patch("src.engine.tts.openai.openai.OpenAI", return_value=fake_openai_client()):
        synthesise("openai", SCRIPT, OPENAI_CONFIG, workdir)

    export = _fake_pydub.empty.return_value.export
    assert export.call_args.kwargs["bitrate"] == "192k"
    assert export.call_args.kwargs["format"] == "mp3"


def test_a_backend_producing_no_audio_raises(workdir):
    from src.engine.tts.audio import concat_to_mp3

    with pytest.raises(TTSError, match="No audio"):
        concat_to_mp3([b"", None], workdir, "episode.mp3")


def test_workdir_is_created_if_it_does_not_exist(workdir):
    assert not workdir.exists()

    with patch("src.engine.tts.openai.openai.OpenAI", return_value=fake_openai_client()):
        output = synthesise("openai", SCRIPT, OPENAI_CONFIG, workdir)

    assert workdir.is_dir() and output.is_file()


# --------------------------------------------------------------------------
# Opt-in live tests
#
# Gated on an explicit flag, NOT on the key being set. Every provider key in
# this repo's .env is present, well-formed and revoked, and CI has no provider
# secrets at all — so a key-presence gate would turn a stale .env into red
# tests rather than skipped ones.
# --------------------------------------------------------------------------

live = pytest.mark.skipif(
    os.getenv("RUN_LIVE_TTS_TESTS") != "1",
    reason="opt-in: set RUN_LIVE_TTS_TESTS=1 and supply a working provider key",
)


@live
@pytest.mark.live_tts
def test_live_elevenlabs_dialogue(tmp_path):
    output = synthesise("elevenlabs", SCRIPT, ELEVEN_CONFIG, tmp_path)

    assert output.is_file()
    assert output.stat().st_size > 10_000, "suspiciously small for four turns"


@live
@pytest.mark.live_tts
def test_live_edge(tmp_path):
    """Needs no API key at all, so this is the cheapest end-to-end check."""
    output = synthesise("edge", SCRIPT, EDGE_CONFIG, tmp_path)

    assert output.is_file()
    assert output.stat().st_size > 10_000


# --------------------------------------------------------------------------
# The ElevenLabs window
# --------------------------------------------------------------------------

def test_live_task_fails_fast_and_legibly_on_elevenlabs():
    """#542 moved the dependency to elevenlabs>=2.x for Text-to-Dialogue, and
    2.x removed `client.generate()` — the one call podcastfy's provider makes.
    Until #543 replaces podcastfy, that path cannot work; it should say so
    rather than surface an AttributeError from inside site-packages after the
    LLM has already been paid for.
    """
    import ast

    tree = ast.parse(Path("src/tasks/podcast_generation.py").read_text())
    messages = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    guard = [m for m in messages if "temporarily unavailable" in m]

    assert guard, "no fail-fast guard for the ElevenLabs window"
    assert any("#543" in m for m in messages), "the guard should name the issue"


def test_podcastfy_elevenlabs_provider_is_indeed_broken_under_the_new_sdk():
    """Guards the premise of the guard above. If a future elevenlabs release
    restores `generate()`, or podcastfy is gone, this fails and the fail-fast
    branch should be revisited rather than left misleading people.
    """
    from elevenlabs.client import ElevenLabs

    assert not hasattr(ElevenLabs(api_key="test"), "generate"), (
        "elevenlabs restored .generate(); podcastfy's ElevenLabs path may work "
        "again — re-check the guard in src/tasks/podcast_generation.py"
    )
    assert hasattr(ElevenLabs(api_key="test"), "text_to_dialogue")


# --------------------------------------------------------------------------
# Edge cases across every backend
# --------------------------------------------------------------------------

EMPTY_SCRIPT = Script(
    title="t", summary="s",
    turns=[{"speaker": "host", "text": "   "}, {"speaker": "guest", "text": ""}],
)


@pytest.mark.parametrize(
    "provider,config",
    [
        ("openai", OPENAI_CONFIG),
        ("elevenlabs", ELEVEN_CONFIG),
        ("gemini", GEMINI_CONFIG),
        ("gemini_multi", GEMINI_CONFIG),
        ("edge", EDGE_CONFIG),
    ],
)
def test_a_script_of_only_blank_turns_is_refused_by_every_backend(
    provider, config, workdir
):
    """Blank turns are stripped before dispatch, so a script of nothing but
    blanks would otherwise send zero requests and assemble zero audio — every
    backend must say so rather than return an empty file."""
    with pytest.raises(TTSError, match="no speakable turns"):
        synthesise(provider, EMPTY_SCRIPT, config, workdir)


def test_serial_path_is_used_when_concurrency_is_one(workdir):
    """A bound of 1 must not pay for a thread pool it cannot use."""
    client = fake_openai_client()

    with patch.object(settings, "ENGINE_TTS_MAX_CONCURRENCY", 1), patch(
        "src.engine.tts.openai.ThreadPoolExecutor"
    ) as pool, patch("src.engine.tts.openai.openai.OpenAI", return_value=client):
        synthesise("openai", SCRIPT, OPENAI_CONFIG, workdir)

    pool.assert_not_called()
    assert client.audio.speech.create.call_count == len(SCRIPT.turns)


def test_gemini_single_speaker_error_becomes_a_provider_error(workdir):
    from google.api_core import exceptions as google_exceptions

    client = MagicMock()
    client.synthesize_speech.side_effect = google_exceptions.DeadlineExceeded("slow")

    with patch(
        "src.engine.tts.gemini.texttospeech.TextToSpeechClient", return_value=client
    ):
        with pytest.raises(TTSProviderError, match="Gemini TTS call failed"):
            synthesise("gemini", SCRIPT, GEMINI_CONFIG, workdir)


def test_elevenlabs_accepts_bytes_as_well_as_a_chunk_iterator(workdir):
    """The SDK's return type is an iterator, but a bytes body is a shape the
    docs also describe; handling only one of them would break on the other."""
    client = MagicMock()
    client.text_to_dialogue.convert = create_autospec(
        _real_dialogue_convert(), side_effect=[MP3]
    )

    with patch("src.engine.tts.elevenlabs.ElevenLabs", return_value=client):
        output = synthesise("elevenlabs", SCRIPT, ELEVEN_CONFIG, workdir)

    assert output.is_file()


def test_elevenlabs_unexpected_audio_type_is_a_provider_error(workdir):
    client = MagicMock()
    client.text_to_dialogue.convert = create_autospec(
        _real_dialogue_convert(), side_effect=[object()]
    )

    with patch("src.engine.tts.elevenlabs.ElevenLabs", return_value=client):
        with pytest.raises(TTSProviderError, match="unexpected audio type"):
            synthesise("elevenlabs", SCRIPT, ELEVEN_CONFIG, workdir)


def test_edge_passes_rate_and_volume_through_to_the_client(tmp_path):
    """Those two live in the stored config's extras; dropping them silently
    ignores a user's pacing choice."""
    import asyncio

    from src.engine.tts.edge import _save

    communicate = MagicMock()

    async def fake_save(path):
        Path(path).write_bytes(MP3)

    communicate.save = fake_save
    destination = tmp_path / "turn.mp3"

    with patch("edge_tts.Communicate", return_value=communicate) as ctor:
        asyncio.run(
            _save("hello", "en-US-AriaNeural", destination,
                  {"rate": "+10%", "volume": "-5%"})
        )

    assert ctor.call_args.kwargs["rate"] == "+10%"
    assert ctor.call_args.kwargs["volume"] == "-5%"
    assert ctor.call_args.args == ("hello", "en-US-AriaNeural")
    assert destination.read_bytes() == MP3


# --------------------------------------------------------------------------
# Google configs legitimately carry no voices
# --------------------------------------------------------------------------

# Exactly what GEMINI_REQUIRED_KEYS permits: model + language_code, no voices.
STORED_GEMINI_CONFIG = {"model": "gemini-2.5-flash-tts", "language_code": "en-US"}


@pytest.mark.parametrize("provider", ["gemini", "gemini_multi"])
def test_a_stored_google_config_without_voices_is_accepted(provider):
    """`GEMINI_REQUIRED_KEYS` is only {model, language_code}, so a row that
    passed write-time validation legitimately has no voices. Rejecting it would
    fail every existing Gemini episode at the #543 cut-over."""
    voices = VoiceConfig.from_tts_config(STORED_GEMINI_CONFIG, provider)

    assert voices.host_voice and voices.guest_voice
    assert voices.host_voice != voices.guest_voice


@pytest.mark.parametrize("provider", ["openai", "elevenlabs", "edge"])
def test_the_other_providers_still_require_voices(provider):
    """Their schemas require voices at write time, so a missing one there is a
    genuinely broken row, not a permitted shape."""
    with pytest.raises(TTSError, match="missing a voice"):
        VoiceConfig.from_tts_config({"model": "whatever"}, provider)


def test_gemini_multi_synthesises_from_a_voiceless_stored_config(workdir):
    client = fake_google_client()

    with patch(
        "src.engine.tts.gemini.texttospeech.TextToSpeechClient", return_value=client
    ):
        output = synthesise("gemini_multi", SCRIPT, STORED_GEMINI_CONFIG, workdir)

    assert output.is_file()
    configs = client.synthesize_speech.call_args.kwargs[
        "voice"
    ].multi_speaker_voice_config.speaker_voice_configs
    assert [c.speaker_id for c in configs] == [
        settings.ENGINE_GEMINI_HOST_VOICE,
        settings.ENGINE_GEMINI_GUEST_VOICE,
    ]


def test_an_explicit_voice_still_wins_over_the_fallback(workdir):
    voices = VoiceConfig.from_tts_config(GEMINI_CONFIG, "gemini_multi")

    assert (voices.host_voice, voices.guest_voice) == ("Kore", "Charon")


# --------------------------------------------------------------------------
# The guard must not break idempotency
# --------------------------------------------------------------------------

def test_elevenlabs_guard_sits_after_the_idempotency_short_circuits():
    """Raising before them would turn a redelivery of an already-complete
    episode into a failure, and the retries-exhausted handler would then
    overwrite a completed episode's status with 'failed'."""
    source = Path("src/tasks/podcast_generation.py").read_text()

    guard = source.index("ElevenLabs generation is temporarily unavailable")
    already_complete = source.index('_skipped_result("already complete")')
    lock = source.index('_skipped_result("concurrent run in progress")')

    assert already_complete < guard, "guard runs before the duplicate check"
    assert lock < guard, "guard runs before the concurrency lock"
