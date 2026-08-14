# Effort review: forking / vendoring podcastfy

**Date:** 2026-08-13 · **Issue:** #446 · **Companion:** [podcastfy-advisory-reachability.md](./podcastfy-advisory-reachability.md)

Requested so the fork decision can be made on its own merits rather than being forced by
security pressure. Per the reachability analysis, the security pressure is **low**: 21 of
22 advisories are inert and the one reachable item is commit-pinned. Nothing here is
urgent. This is a planning document.

## The finding that should drive the decision

**The entire advisory surface traces to one file.**

```
langchain touchpoints across all 19 podcastfy modules: content_generator.py only (25 references)
```

`grep -rln langchain` over the installed package returns exactly one file. The other 18
modules — every TTS provider, every content extractor, all config handling — do not import
langchain at all. What those 25 references do:

| Use | Symbols |
|---|---|
| Model selection | `ChatLiteLLM`, `ChatGoogleGenerativeAI`, `Llamafile` |
| Prompt templating | `ChatPromptTemplate`, `HumanMessagePromptTemplate` |
| Output handling | `StrOutputParser`, LCEL `\|` chaining |
| Prompt fetching | `hub.pull` ×3 |

That is: *pick a model, format a prompt, call it, get a string back.* All 22 alerts —
langchain, langchain-community, langchain-core, langchain-text-splitters, langsmith,
litellm, google-cloud-aiplatform — are the transitive cost of that thin slice.

The corollary matters: **a fork is not "own 3,254 lines." It is "replace ~25 lines of glue
in one file, and inherit the rest unchanged."**

## What we actually use

podcastfy is small: **19 files, 3,254 LOC**.

| Module | LOC | We use it? |
|---|---:|---|
| `content_generator.py` | 911 | **Yes** — `ContentGenerator`, and the only langchain consumer |
| `client.py` | 389 | **Yes** — `generate_podcast` orchestration |
| `text_to_speech.py` | 360 | Yes (via `generate_podcast`) |
| `tts/providers/geminimulti.py` | 337 | Yes — `gemini_multi` |
| `utils/config_conversation.py` | 244 | Yes |
| `content_parser/website_extractor.py` | 165 | **Yes** — imported directly |
| `utils/config.py` | 153 | Yes — also the `.env` loader (see reachability doc) |
| `tts/base.py` | 123 | Yes |
| `content_parser/content_extractor.py` | 133 | Yes (via client) |
| `tts/providers/gemini.py` | 101 | Yes |
| `content_parser/youtube_transcriber.py` | 68 | Yes — YouTube URLs route here |
| `content_parser/pdf_extractor.py` | 67 | **Yes** — imported directly |
| `tts/providers/edge.py` | 50 | Yes |
| `tts/factory.py` | 46 | Yes |
| `tts/providers/openai.py` | 42 | Yes |
| `utils/logger.py` | 34 | Yes |
| `tts/providers/elevenlabs.py` | 29 | Yes |

Effectively all of it. There is no dead weight to drop — the savings do not come from
deleting code, they come from **replacing the langchain layer**.

## What forking buys

1. **All 22 advisories become fixable.** The cap is `podcastfy==0.4.1`'s
   `openai<2.0.0` + `langchain-community<0.4`. Remove the pin and litellm/langchain/
   langsmith can all move to patched versions. Note this is true even if we keep using
   litellm — the cap is podcastfy's, not litellm's.
2. **Drops the runtime LangChain Hub dependency** (GHSA-3644, plus the egress and
   third-party-availability exposure documented in the reachability doc).
3. **Removes packaging defects we inherit.** podcastfy declares **35 runtime
   dependencies**, including `pytest`, `pytest-xdist`, `nbsphinx`,
   `sphinx-autodoc-typehints`, `cython`, `pandoc`, `pandas`, `fuzzywuzzy`,
   `python-levenshtein`. Docs and test tooling in the production closure is why `pytest`
   appears in our CVE list at all, and why `setuptools<76` is capped.
4. **Unblocks signature coupling.** #204's pin exists because task kwargs are coupled to
   the upstream call signature. Owning it removes that constraint permanently.
5. **Upstream is dormant.** 0.4.3 shipped 2025-12-09; nothing in 8 months, and 0.4.0→0.4.2
   had a 13-month gap. We are already de facto unmaintained.

## What forking costs

1. **Ownership of ~3,250 LOC**, most of which is provider glue that breaks when vendor
   APIs change (5 TTS providers, 4 content extractors).
2. **The 911-line `content_generator.py`** is the complex piece — longform chunking with
   contextual linking is the non-trivial logic, and it is the file we would be modifying.
3. **Output-equivalence risk.** Replacing `hub.pull` prompts with local copies changes
   generated content unless the pinned prompts are captured verbatim. Needs a
   before/after comparison on real episodes, which is subjective to evaluate.
4. **No upstream bug fixes** — though at 8 months dormant, this cost is close to zero.
5. **Test burden.** podcastfy ships its own tests we would not inherit cleanly; we would
   be writing coverage for 3k LOC to meet the repo's 85% gate, or carving the vendored
   package out of coverage.

## Staged options

Ordered by cost. Each stage is independently shippable and none forecloses the next.

### Stage 0 — Do nothing (current state)
Advisories documented and enforced by `tests/test_dependency_reachability.py`.
**Cost: zero.** Appropriate while the reachability finding holds.

### Stage 1 — Neutralise `hub.pull` without forking
Capture the four pinned prompts to local files and override
`content_generator_config` (or wrap `ContentGenerator`) so no runtime hub call occurs.
Removes GHSA-3644 exposure, the egress dependency, and the unwrapped `:790` failure mode.
**Estimate: 0.5–1 day**, most of it verifying generated output is unchanged.
**Does not** unpin anything — the other 21 advisories stay ignored (but stay inert).

### Stage 2 — Vendor podcastfy, replace the langchain layer
Copy the 19 modules into `apps/api/src/vendor/podcastfy/` (or a sibling package), then
rewrite the 25 langchain touchpoints in `content_generator.py` against the LiteLLM SDK (or
provider SDKs) directly. Drop `langchain*`, `langsmith`, and the docs/test deps from the
closure; upgrade litellm freely.
**Estimate: 3–5 days** — 1 day vendoring and wiring, 1–2 days on the LLM layer, 1–2 days
on output-equivalence testing across the source types (url/pdf/text, short and longform).
**Clears all 22 advisories permanently.**

### Stage 3 — Full rewrite of the pieces we use
Keep only the behaviours we expose and write them fresh. Highest control, highest cost,
and hard to justify while Stage 2 leaves us with working code.
**Estimate: 2–3 weeks.** Not recommended.

## Recommendation

**Stage 0 now; Stage 2 when there is a reason beyond security.** The security case does not
justify a fork today — that was the question #446 was raised to answer, and the answer is
no. But three non-security forces point the same way, and any one of them should trigger
Stage 2:

- adding an **image** source type (makes GHSA-2g6r live and changes the analysis)
- needing a podcastfy behaviour change that the pinned call signature blocks (#204)
- the `setuptools<76` / `openai<2` caps blocking an unrelated upgrade we actually want

Stage 1 is a reasonable middle step if the LangChain Hub *availability* risk becomes a
concern — a third-party account outage currently degrades or fails generation — but it is
not security-motivated.
