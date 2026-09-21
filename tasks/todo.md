# [P2.18] #541 — Engine step 1: in-repo script generation — ✅ MERGED (PR #573, bc0c188)

Epic #538, step 1 of 3. Depends on #539 (done). Blocks #542, #543.

**Scope guard (from the issue):** this lands the module + unit tests with recorded
provider responses. TTS is #542. Cut-over + dependency removal is #543. The live
Celery task does **not** call this yet.

## Acceptance criteria

- [x] `generate_script` returns a validated `Script` for url/text/pdf-extracted input, short and long-form
- [x] No runtime network call other than the LLM provider
- [x] Prompts in-repo; a test asserts no `langchain`/`litellm` import under `src/engine`
- [x] Transcript persistence helper exists and is covered

## Files

```
apps/api/src/engine/__init__.py            public API re-exports
apps/api/src/engine/models.py              Turn, Script, ConversationConfig
apps/api/src/engine/llm.py                 provider clients (gemini + openai), structured JSON
apps/api/src/engine/script.py              generate_script, chunking, rolling summary, validation
apps/api/src/engine/transcript.py          persist_transcript helper
apps/api/src/engine/prompts/short_form.md
apps/api/src/engine/prompts/long_form.md
apps/api/src/config.py                     engine settings (revive the orphaned validation block)
apps/api/pyproject.toml                    add openai + google-genai as direct deps
apps/api/tests/unit/test_engine_script.py
apps/api/tests/unit/test_engine_transcript.py
apps/api/tests/unit/fixtures/engine/*.json recorded provider payloads
apps/api/tests/test_dependency_reachability.py  + engine import guards
```

## Steps (TDD — test first at each step)

1. **`models.py`** — `Turn(speaker: Literal["host","guest"], text: str)`,
   `Script(title, summary, turns: list[Turn])`, `ConversationConfig` with a default for
   every field and `extra="ignore"` so a `conversation_templates.config` dict (which also
   carries podcastfy-only keys like `text_to_speech`) maps straight in.
   Tests: unknown keys dropped, `None`/partial config yields defaults, speaker literal enforced.

2. **`llm.py`** — `generate_json(prompt, system, config, schema) -> BaseModel`.
   - Gemini: `genai.Client(api_key=...).models.generate_content(model=…, contents=…,
     config=types.GenerateContentConfig(system_instruction=…, temperature=…,
     max_output_tokens=…, response_mime_type="application/json", response_schema=Schema))`
   - OpenAI: `client.chat.completions.parse(model=…, messages=…, response_format=Schema)`
   - Timeout/retries come from the client constructor, not a hand-rolled loop.
   - Raises `EngineError` on a missing API key or an unparseable payload.
   Tests: both providers called with the right kwargs (autospec against the real SDK
   signature, per `tests/unit/test_podcast_generation_task.py`); missing key raises.

3. **Prompts** — `prompts/short_form.md`, `prompts/long_form.md`, loaded with
   `importlib.resources` and `str.format`-rendered from `ConversationConfig`.
   Substance ported from the four pinned Hub prompts (fetched once at dev time from the
   commit hashes in `docs/podcastfy-advisory-reachability.md:151-154`): persona roles,
   conversation style, dialogue structure, engagement techniques, word count, language,
   the "discuss the provided input, do not invent a topic" guardrail, and the long-form
   part-index instructions (open on part 0, wrap up on the last, alternate speakers
   across the seam). Output-format instructions are **not** ported — podcastfy's ask for
   `<Person1>` free text; ours asks for the JSON schema.
   Test: both prompt files ship in the wheel and render with no unreplaced placeholder.

4. **`script.py` — `generate_script(sources, config, longform=False, on_progress=None)`**
   - Short form: one call, validate, one retry on schema-or-validation failure.
   - Long form: chunk on sentence boundaries (`ENGINE_MAX_CHUNKS`, `ENGINE_MIN_CHUNK_CHARS`
     — same 8/600 defaults podcastfy used), then per chunk pass **only** the accumulated
     per-chunk summaries plus the last two turns as context. Each chunk call already
     returns a `summary` field, so the rolling summary costs no extra LLM call. This is
     the fix for the O(n²) full-transcript resend.
   - `on_progress(stage, percent)` fires per chunk — the seam #543 needs for real
     extracting → scripting → synthesising progress.
   - Validation (ported from the deleted `ScriptGenerationService._validate_transcript`):
     both speakers present with non-empty text, ≥ `MIN_TRANSCRIPT_WORDS` combined,
     ≥ `MIN_CONVERSATION_TURNS` speaker transitions, neither speaker above
     `MAX_SPEAKER_IMBALANCE_PERCENT` of total words, no `AI_ARTIFACT_PATTERNS` hit.
   Tests: short form happy path; long form stitches N chunks and never passes a prior
   chunk's turns as context; each validation rule rejects; retry succeeds on the second
   response and gives up on the second failure; `on_progress` called once per chunk.

5. **`transcript.py` — `persist_transcript(script, user_id, episode_id)`** → S3 key
   `podcasts/user-{user_id}/episode-{episode_id}.transcript.json` via the existing
   `build_podcast_s3_key` sibling convention, with the `LOCAL_AUDIO_STORAGE_PATH`
   fallback mirroring `_persist_local_audio`. Returns the path/key to write into
   `episode.transcript_path` (today always `None` — #309).
   Tests: S3 path and local-fallback path, JSON round-trips back into `Script`.

6. **`config.py`** — add `ENGINE_LLM_PROVIDER` (`gemini` default, matching today's live
   behaviour), `ENGINE_GEMINI_MODEL`, `ENGINE_OPENAI_MODEL`, `ENGINE_MAX_OUTPUT_TOKENS`,
   `ENGINE_MAX_CHUNKS`, `ENGINE_MIN_CHUNK_CHARS`, `OPENAI_API_TIMEOUT`,
   `OPENAI_API_MAX_RETRIES`. Update `.env.example`.

7. **`test_dependency_reachability.py`** — add the two guards, matching the file's
   existing Pattern A/B: a source grep over `src/engine/**.py` for `langchain`/`litellm`
   with a floor-count assertion, and a subprocess probe that imports the engine and
   asserts neither appears in `sys.modules`.

8. **`pyproject.toml`** — `openai` and `google-genai` become direct deps (both are
   already in the closure transitively; `openai` stays under podcastfy's `<2` ceiling
   until #543 removes the pin).

## Decisions made autonomously (no architectural fork)

- **Model defaults verified against live provider docs today, not memory:**
  `gemini-3.5-flash` (GA, balances cost/quality; podcastfy's `gemini-1.5-pro-latest` is a
  deprecated alias) and `gpt-5.6-terra` (OpenAI's current "balances intelligence and
  cost" tier). Both are settings, so #543 can retune without a code change.
- **`generate_script` is synchronous.** Celery tasks here are sync, and `asyncio.run`
  inside a Celery worker is a known trap in this repo.
- **Rolling summary is reused from the `Script.summary` the model already returns**
  per chunk, rather than a separate summarisation call. No extra spend.
- **Reused `MAX_SPEAKER_IMBALANCE_PERCENT` (80%) instead of adding a ratio knob.**
  The issue says "within a ratio"; an 80%-of-total cap is that constraint, and the
  setting already exists in `config.py` (orphaned since #539 deleted its only consumer).
  Same for `MIN_TRANSCRIPT_WORDS`, `MIN_CONVERSATION_TURNS`, `AI_ARTIFACT_PATTERNS`.
- **Tightened the `AI_ARTIFACT_PATTERNS` default.** The inherited list contains
  `"based on the"` and `"according to my"`, which match ordinary podcast speech and would
  reject good scripts. The setting has had no consumer since #539, so tightening it now
  has no blast radius. New list targets refusal/assistant boilerplate only.
- **Turn count is a floor, not a range.** "Within bounds" upper-bounds naturally via
  `word_count`; a separate max would reject long-form by construction.
- **One retry on schema-or-validation failure, not a configurable count.**
  `TRANSCRIPT_VALIDATION_MAX_RETRIES` stays unused rather than gaining a second meaning.

## Known risks

- `filterwarnings = error` — a new SDK import that warns will fail the suite; narrow
  ignore with a comment if so (precedent: the `google.generativeai` FutureWarning entry).
- `google-genai` is pinned low (1.2.0) by the current closure; `response_schema` is
  verified present at that version.


---

## Outcome

Merged 2026-09-21 as PR #573 (`bc0c188`), 7 commits squashed. 1863 backend tests
passing (baseline 1802), `src/engine` at 98–100% per file, 16/16 mutations caught,
all 13 CI checks green, GLM bot verdict "no defects found".

Deferred, filed rather than dropped: #574 (long-form loses paid chunks on a
transient provider failure), #575 (`_persist_local_audio` path join), #576
(output-side injection screening).

Demo: `apps/api/docs/demos/issue541-engine-script-generation.md`.

Open operational item: the dev `GEMINI_API_KEY` is rejected by Google, so nothing
here has been exercised against a live provider.
