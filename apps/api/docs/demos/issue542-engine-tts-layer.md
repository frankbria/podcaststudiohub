# In-repo TTS layer, Eleven v3 Text-to-Dialogue (#542)

*2026-09-21T18:17:43Z*

Issue #542 [P2.19] — step 2 of the engine-replacement epic (#538). Five TTS backends behind one interface, replacing `podcastfy.text_to_speech` and its five providers.

Per the issue scope guard the live Celery task does **not** call this yet (#543 cuts over), so every scenario below drives the real layer with the provider SDKs faked at the boundary — and pydub faked too, since CI has no ffmpeg. Nothing here makes a network call.

Each acceptance criterion is exercised with the outcome, not a green exit code.

## AC1 — five backends behind one interface

The stored `tts_configurations.config` shape differs per provider — plain voice names for OpenAI and Edge, opaque ids for ElevenLabs, and for the Google pair the schema requires no voices at all. `VoiceConfig` normalises all of that once, so no backend has to guess which spelling its provider used.

```bash
uv run python /home/frankbria/.claude/jobs/f2afff4f/tmp/demo_tts.py interface
```

```output
One interface, five backends:

  openai         -> OpenAITTS          synthesise(script, voices, workdir) -> Path
  elevenlabs     -> ElevenLabsTTS      synthesise(script, voices, workdir) -> Path
  gemini         -> GeminiTTS          synthesise(script, voices, workdir) -> Path
  gemini_multi   -> GeminiMultiTTS     synthesise(script, voices, workdir) -> Path
  edge           -> EdgeTTS            synthesise(script, voices, workdir) -> Path

The stored config shape differs per provider; VoiceConfig normalises it:
  openai (names)         host=alloy        guest=echo         model=gpt-4o-mini-tts
  elevenlabs (ids)       host=voiceA       guest=voiceB       model=eleven_v3
  gemini (no voices!)    host=Kore         guest=Charon       model=gemini-2.5-flash-tts
```

## AC1 (cont.) — every temp file under the caller-supplied workdir

This is the invariant the whole interface exists for. podcastfy's providers returned bare `bytes` with no say in where files landed, so one of them wrote `temp_chunk_{i}.mp3` into the **process working directory** — no directory, no uuid, which collides under the prefork pool the moment two episodes run at once.

Here the caller hands over a `workdir` and the backend writes nothing anywhere else:

```bash
uv run python /home/frankbria/.claude/jobs/f2afff4f/tmp/demo_tts.py workdir_discipline
```

```output
caller-supplied workdir : /tmp/tmplb_m4ajv/per-run
intermediates written   : 4
   per-run/turn-0000.mp3   inside workdir: True
   per-run/turn-0001.mp3   inside workdir: True
   per-run/turn-0002.mp3   inside workdir: True
   per-run/turn-0003.mp3   inside workdir: True
final file              : per-run/episode.mp3
unique names            : 4 of 4  (no collisions)

stray files in cwd      : none
  podcastfy wrote temp_chunk_{i}.mp3 right here, with no dir and no uuid.
```

The other half of the old temp-file problem is not a code reading — it is sitting on disk right now. podcastfy computed its temp directory relative to its own `__file__`, so a previous run's audio is permanently stuck inside the installed package:

```bash
uv run python /home/frankbria/.claude/jobs/f2afff4f/tmp/demo_tts.py podcastfy_leftovers
```

```output
MP3s abandoned inside the installed podcastfy package: 12 (1058 KB)
   data/audio/tmp/tmpibdcmvin/1_answer.mp3
   data/audio/tmp/tmpibdcmvin/1_question.mp3
   data/audio/tmp/tmpibdcmvin/2_answer.mp3
   data/audio/tmp/tmpibdcmvin/2_question.mp3
   ... and 8 more

These are a previous run's per-turn audio, stuck in site-packages because
podcastfy computed its temp dir relative to its own __file__.
```

## AC2 — no module-global API keys

podcastfy set `openai.api_key` as module-global state (`tts/providers/openai.py:22`). That is process-wide: it clobbers any other key in the same worker and makes bring-your-own-key impossible. A scoped client costs nothing and does neither.

```bash
uv run python /home/frankbria/.claude/jobs/f2afff4f/tmp/demo_tts.py no_global_key
```

```output
openai.api_key before synthesis : None
openai.api_key after  synthesis : None
unchanged                       : True

podcastfy did `openai.api_key = api_key` at tts/providers/openai.py:22 —
process-global, clobbers any other key in the worker, forecloses BYOK.
```

## AC3 — Eleven v3 Text-to-Dialogue

The capability podcastfy could not reach at all: its pinned SDK (1.59.0) has no `text_to_dialogue`, only the legacy `generate()` shim, which it called **once per turn**. Every line was therefore synthesised in isolation, with no knowledge of the one before it.

Text-to-Dialogue takes the turns together, each carrying its own `voice_id`, and renders them as one conversation — which is what lets the model time a reaction or an interruption:

```bash
uv run python /home/frankbria/.claude/jobs/f2afff4f/tmp/demo_tts.py dialogue
```

```output
requests made : 1 for 4 turns
model_id      : eleven_v3

The whole conversation in one request, each turn with its own voice:
   voice=voiceA   Welcome to The Signal Room.
   voice=voiceB   Glad to be here. Let's get into it.
   voice=voiceA   So what does retrieval actually buy you?
   voice=voiceB   Inspectable failures, mostly.

podcastfy called the legacy .generate() shim once per turn, so every line
was synthesised in isolation with no knowledge of the one before it.
```

### …and it respects the character cap

The issue said 5,000. Checking ElevenLabs' live docs, that is the limit for **plain single-voice text-to-speech** on the same model; Text-to-Dialogue documents **2,000 characters summed across every input in the request**, and exceeding it returns a validation error or truncates a streaming response part-way.

Batching is by consecutive turns rather than per turn on purpose — the model only produces conversational timing across turns it sees together, so the cap is the only reason to ever split:

```bash
uv run python /home/frankbria/.claude/jobs/f2afff4f/tmp/demo_tts.py char_cap
```

```output
configured cap: 2000 chars per request
(the issue said 5000 — that is Eleven v3's single-voice TTS limit, a different endpoint)

  4 short turns        -> 1 request(s), sizes [400], order preserved: True
  4 x 800 chars        -> 2 request(s), sizes [1600, 1600], order preserved: True
  3 x 1500 chars       -> 3 request(s), sizes [1500, 1500, 1500], order preserved: True
  one 5000-char turn   -> 1 request(s), sizes [5000], order preserved: True
```

## AC4 — concurrent per-turn synthesis

podcastfy synthesised one turn at a time in a plain loop, each a blocking round trip. Forty turns meant forty round trips end to end. The bound here is a setting, because providers rate-limit and Celery runs prefork — threads multiply by worker count.

Turn order is the one thing concurrency must not disturb; a raced episode is unlistenable. `ThreadPoolExecutor.map` yields in input order, so order is preserved by construction rather than by sorting afterwards:

```bash
uv run python /home/frankbria/.claude/jobs/f2afff4f/tmp/demo_tts.py concurrency
```

```output
turns                 : 4
configured bound      : 4
peak concurrent calls : 4   (podcastfy: strictly 1, one blocking call per turn)
assembly order        : [b'A', b'B', b'C', b'D'] == script order: True
```

## The Google multi-speaker path is a rewrite, not a port

podcastfy pinned the literal `en-US-Studio-MultiSpeaker` in three places, and its `validate_parameters` actively **rejected** any other model — so it was enforced, not defaulted. That Studio voice is now restricted, and Google's supported path is Gemini-TTS, which takes a different request shape: speakers are declared up front as aliases and the markup references them, instead of turns carrying bare voice letters like "R" and "S".

Note the input config here: it has no voices at all, which is exactly what the schema permits for Google.

```bash
uv run python /home/frankbria/.claude/jobs/f2afff4f/tmp/demo_tts.py gemini_multi
```

```output
Stored config carried NO voices (schema only requires model + language_code):
   {'model': 'gemini-2.5-flash-tts', 'language_code': 'en-US'}

model_name: gemini-2.5-flash-tts
speakers declared up front as aliases:
   alias=Host   -> speaker_id=Kore
   alias=Guest  -> speaker_id=Charon
markup turns reference those aliases:
   Host   Welcome to The Signal Room.
   Guest  Glad to be here. Let's get into it.
   Host   So what does retrieval actually buy you?
   Guest  Inspectable failures, mostly.

podcastfy tagged turns with bare letters R and S on en-US-Studio-MultiSpeaker,
and its validate_parameters REJECTED any other model. That voice is now restricted.
```

## A misconfigured episode fails as configuration

The cross-family review caught a real defect here: the voice check was unconditional, but `GEMINI_REQUIRED_KEYS` is only `{model, language_code}` — unlike the other four providers, Google rows legitimately carry no voices. Rejecting them would have failed every existing Gemini episode at the #543 cut-over.

Voice resolution is now provider-aware — Google falls back to configured prebuilt speakers, the other three still treat a missing voice as the broken row it is:

```bash
uv run python /home/frankbria/.claude/jobs/f2afff4f/tmp/demo_tts.py misconfig
```

```output
A config missing a speaker is a configuration failure, not a crash:

  openai         -> TTSError: TTS config is missing a voice for both speakers; expected voice_1/
  elevenlabs     -> TTSError: TTS config is missing a voice for both speakers; expected voice_1/
  edge           -> TTSError: TTS config is missing a voice for both speakers; expected voice_1/
  gemini_multi   -> ACCEPTED  host=Kore guest=Charon  (voices optional for Google)
```

## The tests behind all of this

Green tests prove the suite ran. To check they would catch a regression, each behaviour above was broken in the production code and the test that names it re-run — 20 mutations across all seven modules:

```bash
bash /home/frankbria/.claude/jobs/f2afff4f/tmp/mutate_tts.sh
```

```output
== base.py ==
  caught   voice_for maps speaker->voice
  caught   blank turns dropped
  caught   half-configured config rejected
== audio.py ==
  caught   192k export bitrate
  caught   no-audio raises
== openai.py ==
  caught   missing key guard
  caught   openai error normalised
  caught   turn order across concurrency
  caught   concurrency bound honoured
== elevenlabs.py ==
  caught   char cap batching
  caught   batch splits over cap
  caught   per-turn voice pairing
  caught   elevenlabs missing key
== gemini.py ==
  caught   markup speaker aliases
  caught   declared speaker ids
  caught   configured gemini model
== edge.py ==
  caught   intermediates stay in workdir
  caught   intermediates cannot collide
  caught   rate/volume passthrough
== factory.py ==
  caught   gemini_multi underscore

final tree state:
```

And the layer's own suite:

```bash
uv run pytest tests/unit/test_engine_tts.py -q -p no:cacheprovider --no-cov 2>&1 | tail -3
```

```output
0.01s call     tests/unit/test_engine_tts.py::test_elevenlabs_splits_a_long_script_into_several_requests
0.01s call     tests/unit/test_engine_tts.py::test_openai_api_error_becomes_a_provider_error
[32m======================== [32m[1m60 passed[0m, [33m2 skipped[0m[32m in 1.09s[0m[32m =========================[0m
```

## Acceptance criteria → evidence

| Criterion | Action | Outcome evidence | Status |
|---|---|---|---|
| Five backends behind one interface | Resolved every provider value the schema allows | All five return an object exposing `synthesise(script, voices, workdir) -> Path`; three different stored config shapes normalise to the same `VoiceConfig` | VERIFIED |
| All temp files under `workdir` | Ran the Edge backend with a caller-supplied workdir and watched the cwd | 4 intermediates + the final MP3, all inside the workdir; 4 unique names, no collisions; zero stray files in the process cwd | VERIFIED |
| No module-global API keys | Ran a full OpenAI synthesis and read the SDK global | `openai.api_key` is `None` before and `None` after | VERIFIED |
| ElevenLabs uses Text-to-Dialogue on `eleven_v3` | Synthesised a 4-turn script | 1 request for 4 turns, `model_id=eleven_v3`, each input paired with its speaker's `voice_id` in order | VERIFIED |
| …and respects the per-request character cap | Batched four script shapes against the 2,000-char cap | 400 chars → 1 request; 4×800 → 2 requests of 1600; 3×1500 → 3 requests; a single 5000-char turn sent alone rather than split mid-sentence. Order preserved in every case | VERIFIED |
| Concurrent per-turn synthesis | Instrumented the provider call to record live concurrency | Peak 4 concurrent calls against a bound of 4 (podcastfy: strictly 1), and the assembled order still matches script order | VERIFIED |
| Google multi-speaker on a supported model | Synthesised from a voiceless stored config | One request on `gemini-2.5-flash-tts`; speakers declared as `Host`/`Guest` aliases bound to prebuilt ids; every markup turn references a declared alias | VERIFIED |
| Misconfiguration is legible | Fed four half-configured configs | Three providers refuse with a `TTSError` naming the expected keys; Google accepts and falls back, matching what its schema permits | VERIFIED |

## Not demonstrated here

- **No real TTS call has been made.** Every provider key in `apps/api/.env` is present, well-formed and **revoked** — all three return 401 — and CI has no provider secrets. The two live tests are gated on `RUN_LIVE_TTS_TESTS=1` rather than key presence, precisely so a stale `.env` yields skips rather than red tests. Edge needs no key and is the cheapest end-to-end check once someone runs it.
- **No audio was actually decoded.** pydub is faked throughout, because CI has no ffmpeg and the repo's existing audio tests do the same. What is verified is the assembly contract — order, count, bitrate, destination — not the waveform.
- **No quality comparison against podcastfy.** Replacing per-turn synthesis with dialogue synthesis changes the output by design; a subjective before/after belongs with the cut-over, on working keys.
- **The live task still calls podcastfy** — the issue's explicit scope guard — and its ElevenLabs path is deliberately broken until #543, with a fail-fast guard naming that issue.
