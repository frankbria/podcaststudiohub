# [P2.19.2] #578 — Google Cloud TTS credential wiring — PR #613

Previous plan (#542) is in git history at `9ace356`.

## Acceptance criteria

- [x] A host with `GOOGLE_CLOUD_CREDENTIALS` set can synthesise with `gemini` and `gemini_multi` without ADC present
- [x] A host with neither set fails with the existing clear `TTSProviderError`, not a stack trace
- [x] `.env.example` documents the expected format

## Decision (autonomous — no fork)

The setting accepts **either** the service-account JSON itself (value starts with `{`) or a
path to the JSON file. The existing `.env.example` already says "path"; secrets stores and PM2
env pass inline JSON more easily. Both cost one branch.

A separate setting is not redundant with `GOOGLE_APPLICATION_CREDENTIALS`: pydantic reads
`apps/api/.env` into `settings` without exporting it to `os.environ`, so ADC never sees it.

## Steps

1. Tests first (`tests/unit/test_engine_tts.py`): real `TextToSpeechClient` built from a
   generated service-account key (no network at construction), with ADC made to fail —
   inline JSON, file path, and a malformed value / missing file → `TTSProviderError`
   that does not echo the credential.
2. `src/engine/tts/gemini.py::_client()` — build credentials from the setting, fall back to ADC
   when unset; one helper serves both backends.
3. `.env.example` (api + root) — document both forms and the ADC fallback.
4. Platform-level credential note (BYOK lands here if it ever comes for Google) — in the code comment.
