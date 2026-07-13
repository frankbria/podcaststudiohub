# Podcastfy 0.4.1 → 0.4.3 upgrade evaluation (issue #363)

**Date**: 2026-07-13
**Verdict**: **Defer.** Stay pinned on `podcastfy==0.4.1`. The upgrade breaks app
startup out of the box (undeclared `playwright` import), delivers no functional
benefit to any code path this product uses, and does not clear the two CVEs riding
on the langchain pin.

## Method

Upstream publishes no git tags past `v0.4.0`, so the evaluation diffed the PyPI
sdists (`podcastfy-0.4.1` / `0.4.2` / `0.4.3`), then ran an empirical spike on a
branch: bump the pin, `uv lock && uv sync --all-extras`, run
`tests/test_imports.py` + `tests/unit/test_podcast_generation_task.py`
(the #204 signature guards).

## What changed upstream

All substantive changes are in **0.4.2**; 0.4.3 only bumps `httpx ^0.27.2 → ^0.28.1`
in its own pyproject. (`podcastfy.__version__` still reports `"0.4.2"` in the 0.4.3
sdist — upstream release hygiene is loose.)

| Area | Change | Impact on us |
|---|---|---|
| `client.py` (`generate_podcast`) | **Byte-identical** to 0.4.1 | None — the #204 Celery kwarg coupling is signature-safe |
| `content_generator.py` | Default `model_name` `gemini-1.5-pro-latest` → `gemini-2.5-flash` (only hunk) | None — we pass `model_name` explicitly (`GEMINI_MODEL_NAME` env) in `script_generation_service.py` |
| `content_parser/website_extractor.py` | `extract_content` now fetches via Playwright headless Chromium; **imports `playwright.sync_api` at module top** | **Breaks import.** We import `WebsiteExtractor` in `content_extraction_service.py` and the `main.py` startup guard. We never call `extract_content` (bypassed for SSRF safety, #206/#234); the helpers we do use (`normalize_url`, `remove_unwanted_elements`, `clean_content`, `user_agent`, `timeout`) are unchanged |
| `content_parser/content_extractor.py` | Topic grounding rewritten on `google-genai` / `gemini-2.5-flash` (old path used retired `gemini-1.5-flash-002`) | None — the `topic=` path is not wired from our router |
| `tts/providers/gemini.py` | Parses `language_code` from voice name; drops hardcoded `en-US` + `FEMALE` gender | None for our current providers (`openai`, `gemini_multi`→`geminimulti`) |
| `pyproject` deps | `openai ^1.56` (still <2), `httpx ^0.28.1`, `edge-tts 6→7` (major), `google-genai ^1.46` added | Lock churn (see spike); **`playwright` NOT declared** despite the top-level import — upstream packaging bug |
| Misc | New `podcastfy/api/fast_app.py` (unused), default LLM config → gemini-2.5-flash, ending message text | None |

## Spike results

`uv lock` resolves cleanly: `edge-tts 6.1.19→7.2.8`, `google-genai 1.2.0→1.75.0`,
`httpx 0.27.2→0.28.1`, `langchain-google-vertexai 2.0.7→2.1.2`, plus new transitives
`bottleneck`, `numexpr`, `pyarrow 21`, `tabulate`, `validators`.

But the import guard fails immediately:

```
tests/unit/test_podcast_generation_task.py:27: from podcastfy.client import generate_podcast
  → podcastfy/content_parser/website_extractor.py:16: from playwright.sync_api import sync_playwright
  → ModuleNotFoundError: No module named 'playwright'
```

Every import of `podcastfy.client` or the content parsers fails, so the API won't
start. This is exactly why Dependabot #356 failed backend tests, coverage, and e2e.
Working around it means adding `playwright` (plus Chromium binaries on CI + VPS if
the code path ever runs) as our own dependency to patch an upstream packaging bug.

## CVE position (unchanged by the upgrade)

0.4.3 still pins `langchain >=0.3.3,<0.4.0`, so:

- **PYSEC-2026-2193** (langchain-core, fixed only in 1.2.22) — still unreachable
- **PYSEC-2026-2562 / CVE-2026-26013** (SSRF in `ChatOpenAI.get_num_tokens_from_messages`,
  fixed only in langchain-core 1.2.11; method not called by podcastfy or us) — still unreachable

The pip-audit ignore list in `scripts/security-audit.sh` is capped to podcastfy's
requirement set and stays exactly as-is while we remain on 0.4.1.

## Decision

Cost (new prod dependency to work around an upstream bug, a major edge-tts bump,
five new transitives, re-verification of the full generation chain) buys **zero**
user-visible or security benefit. Defer.

**Re-evaluate when upstream ships a release that either:**
1. supports **langchain 1.x** — this is the real payoff: it would clear
   PYSEC-2026-2193 / PYSEC-2026-2562 and let the pip-audit ignore list shrink, or
2. declares its imports correctly (playwright) so the upgrade is at least drop-in, or
3. changes `generate_podcast` / `ContentGenerator` signatures we depend on
   (would show up in `test_podcast_generation_task.py` guards on any future spike).

Dependabot keeps ignoring `podcastfy` (per #363). When re-evaluating, run
`@dependabot unignore dependency` on a podcastfy PR or repeat the spike above.
