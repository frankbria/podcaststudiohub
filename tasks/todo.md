# [P2.19] #542 — Engine step 2: in-repo TTS layer

Epic #538, step 2 of 3. Depends on #541 (`Script`/`Turn`, merged as PR #573).
Blocks #543. Previous plan for #541 is in git history at `5b43ab1`.

**Scope guard (from the issue):** five backends behind one interface, unit tests with
recorded responses plus opt-in live tests. **No cut-over** — `generate_podcast_task`
still calls podcastfy until #543.

## Acceptance criteria

- [ ] Five backends behind one interface; all temp files under `workdir`
- [ ] No module-global API keys; a test asserts `openai.api_key` is untouched after synthesis
- [ ] ElevenLabs backend uses Text-to-Dialogue on `eleven_v3` and respects the per-request character cap
- [ ] Concurrent per-turn synthesis where the backend is single-speaker

## Decisions taken before writing code

**1. Override podcastfy's `elevenlabs<2` cap — approved by the user.**
`text_to_dialogue` exists only in elevenlabs 2.x, and 2.x removed `.generate()`, which is
exactly what podcastfy's provider calls (`tts/providers/elevenlabs.py:21`). Verified by
installing 2.68.0 into a throwaway venv: `text_to_dialogue` present, `generate` absent.
So `[tool.uv] override-dependencies` gains `elevenlabs>=2.68.0`, the same mechanism
already used there for setuptools/wheel.

Consequence, accepted: **podcastfy's ElevenLabs path breaks between this PR and #543.**
To keep that legible rather than mysterious, `generate_podcast_task` gets a guard that
fails fast with a message naming #543, instead of surfacing
`AttributeError: 'ElevenLabs' object has no attribute 'generate'`.

**2. Three corrections to the issue's design, from checking live provider docs.**
Each would otherwise have shipped a defect:

| Issue says | Actually |
|---|---|
| chunk to stay under 5,000 chars/request | Text-to-Dialogue's documented cap is **2,000 chars per request** across all inputs. 5,000 is Eleven v3's *single-voice TTS* limit — a different endpoint. |
| gemini multi-speaker on `en-US-Studio-MultiSpeaker` | That Studio voice is restricted/deprecated. The supported path is **Gemini-TTS** (`gemini-2.5-flash-tts` / `gemini-2.5-pro-tts`, both GA), with a *different* request shape: `MultiSpeakerVoiceConfig` carrying `speaker_alias`/`speaker_id`, not bare `Turn.speaker` strings. |
| (openai) podcastfy's `tts-1-hd` | `gpt-4o-mini-tts` is current and is the only model honouring `instructions`. `tts-1-hd` still works, so it stays selectable. |

**3. Live tests gate on an explicit opt-in flag, not key presence.**
All three provider keys in `apps/api/.env` are present, well-formed, and **revoked** (401),
and CI has no provider secrets at all. Gating on "is the key set?" would turn a stale
`.env` into red tests. Gate on `RUN_LIVE_TTS_TESTS=1`; register the marker in `pytest.ini`
(`--strict-markers` is on, so an unregistered marker fails collection outright).

**4. `factory.py` holds flat `if provider == ...` dispatch**, matching `llm.py`, rather than
a registry. The issue asks for a factory module; the engine's established style is flat
dispatch. Both satisfied.

**5. Audio is mp3 @ 192k**, matching `audio_composition.py`. podcastfy was inconsistent
(320k multi-speaker, library default single-speaker).

**6. Bounded `ThreadPoolExecutor` for per-turn backends.** No precedent in `src/`, but
Celery runs prefork, so threads inside a worker process are safe, and the issue asks for
it. The bound is a setting, not a literal.

## Files

```
apps/api/src/engine/tts/__init__.py     public surface
apps/api/src/engine/tts/base.py         TTSBackend protocol, VoiceConfig, TTSError/TTSProviderError
apps/api/src/engine/tts/audio.py        concat + export helper, workdir discipline
apps/api/src/engine/tts/factory.py      flat provider dispatch
apps/api/src/engine/tts/elevenlabs.py   Text-to-Dialogue, eleven_v3, char-capped batching
apps/api/src/engine/tts/gemini.py       gemini (single) + gemini_multi (Gemini-TTS markup)
apps/api/src/engine/tts/openai.py       scoped client, concurrent per-turn
apps/api/src/engine/tts/edge.py         asyncio.run per call, concurrent, no nest_asyncio
apps/api/src/config.py                  ENGINE_TTS_* settings
apps/api/pyproject.toml                 direct deps + the elevenlabs override
apps/api/src/tasks/podcast_generation.py  fail-fast guard for the ElevenLabs window
apps/api/tests/unit/test_engine_tts.py
apps/api/tests/unit/fixtures/engine/tts/
apps/api/pytest.ini                     register the live marker
```

## Steps (TDD — test first)

1. **`base.py`** — `VoiceConfig.from_tts_config(provider, config)` mapping the flat stored
   dict (`voice_1`/`voice_2`, `voice_1_id`/`voice_2_id`, `model`, `language_code`, plus
   provider extras like `speed`/`stability`/`rate`). `TTSBackend` Protocol with
   `synthesise(script, voices, workdir) -> Path`. `TTSError(EngineError)` /
   `TTSProviderError(TTSError)` mirroring `llm.py`'s taxonomy.
2. **`audio.py`** — concatenate per-turn MP3 blobs into one MP3 under `workdir` at 192k via
   pydub. Tests patch `pydub.AudioSegment` (CI has no ffmpeg).
3. **`openai.py`** — scoped `OpenAI(api_key=…)`, `audio.speech.create`, per-turn, bounded
   pool. A test asserts `openai.api_key` is still unset afterwards.
4. **`edge.py`** — `edge_tts.Communicate(...).save()` inside one `asyncio.run` per call, no
   `nest_asyncio`, output into `workdir`.
5. **`gemini.py`** — single-speaker per-turn, and multi-speaker via `MultiSpeakerMarkup` +
   `MultiSpeakerVoiceConfig` on a Gemini-TTS model from settings.
6. **`elevenlabs.py`** — `client.text_to_dialogue.convert(inputs=[DialogueInput(...)])`,
   batching turns under the char cap, concatenating batches. Audio tags pass through.
7. **`factory.py`** + `__init__.py`, settings, deps, the podcastfy guard, marker registration.

## Risks

- **Overriding the cap may perturb the rest of the closure.** `elevenlabs` is imported only
  by podcastfy's own elevenlabs provider, so blast radius should be that one file — but
  `main.py`'s startup check imports podcastfy, so the whole suite must stay green.
- **`uv` may refuse the override** if something else conflicts. Fall back to raising the
  floor in `dependencies` and letting the override resolve it.
- Gemini-TTS model ids are newer than most training data; they came off Google's current
  docs and go into settings with the source cited, per the #541 precedent.
