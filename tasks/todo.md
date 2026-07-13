# #363 [P4.5] Evaluate podcastfy 0.4.1 → 0.4.3 upgrade

## Findings so far (Phase 2)
- Upstream repo has no 0.4.1+ tags; evaluated via PyPI sdist diff 0.4.1 → 0.4.3.
- `podcastfy/client.py` (our `generate_podcast` entrypoint, #204 coupling): **byte-identical**. No signature risk.
- `ContentGenerator`: only default `model_name` changed (`gemini-1.5-pro-latest` → `gemini-2.5-flash`); we pass it explicitly (env `GEMINI_MODEL_NAME`). `generate_qa_content` unchanged.
- `PDFExtractor`: unchanged. `WebsiteExtractor` helpers we use (normalize_url, remove_unwanted_elements, clean_content, user_agent, timeout): unchanged.
- **Breaking**: 0.4.3 `website_extractor.py` imports `playwright.sync_api` at module top but playwright is NOT a declared dependency (upstream packaging bug). Our `main.py` import guard + `content_extraction_service.py` import `WebsiteExtractor` → app import fails unless WE add playwright (+ chromium binaries in CI/VPS).
- `content_extractor.py` now imports `google.genai` top-level; declared (`google-genai ^1.46`) — our lock has 1.2.0, would bump.
- Dep bumps: openai ^1.56 (still <2), httpx ^0.28.1 (we lock 0.27.2), edge-tts 6→7 (major).
- langchain still `<0.4` → PYSEC-2026-2193 / PYSEC-2026-2562 NOT cleared by 0.4.3 (as predicted in issue comments).
- Functional gains for US: ~none. Topic-grounding fix (google-genai/gemini-2.5) only helps `topic=` path — not wired from our router. Playwright fetching only helps `extract_content`, which we deliberately bypass (SSRF #206/#234). Gemini TTS language-code fix only for google-cloud TTS voices.

## Plan
1. [x] Upstream changelog/diff review (above)
2. [x] Empirical spike on feature branch: bump pin → `uv lock` → `uv sync` → run test_imports + signature-guard tests. Record exact failure/success.
3. [x] Verdict (DEFER — evidence: playwright ModuleNotFoundError on import, zero gain, CVEs uncleared) from evidence:
   - If upgrade is drop-in + low cost → complete checklist (caps, CLAUDE.md, full suite, e2e generation).
   - If upgrade costs (playwright+chromium in prod, dep churn) exceed ~zero benefit → **defer**: write evaluation doc (`apps/api/docs/`), update CLAUDE.md pin note + security-audit.sh comment if needed, PR the docs, comment verdict on issue, close.
4. [x] Quality gates, PR #395, showboat demo, merged 2026-07-13. Issue #363 closed.

## Review
SHIPPED via PR #395 (squash 74f9073). Verdict: defer upgrade. Deliverables: apps/api/docs/podcastfy-0.4.3-evaluation.md, CLAUDE.md engine note, security-audit.sh comment fix. Spike reverted; 0.4.1 env verified green (32 guard tests).
