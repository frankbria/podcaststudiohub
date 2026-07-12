# Issue #314 — Multi-modal input scope-down to URL/Text/PDF (P4.2)

Status: SHIPPED — merged 2026-07-12 as 2caa0fb via PR #377; issue #314 closed.

CodeRabbit plan chose the scope-down path (option 2): align every layer to the
genuinely supported set (url, text, pdf), surface the already-built PDF upload
backend in the web UI, and fix overstated copy/docs. No architectural fork.

## Plan adaptations (verified against current code, 2026-07-11)

1. **PDF backend already done** (PR #210/#242): upload endpoint
   `POST /episodes/{episode_id}/content/upload` (routers/content.py:136-197),
   S3 extraction, full test suite. Nothing to build server-side except the
   validator `else` and message tweaks.
2. **Frontend has no PDF at all**: `contentSourceSchema` is `z.enum(["url","text"])`
   (validation.ts:32); dialog toggle at page.tsx:660-686; hint text at :708.
   Work = ADD pdf, not remove youtube/image/topic (never existed client-side).
3. **No web API client layer** (deleted in #264): use inline `fetch` with
   `FormData` to `/api/proxy/episodes/{id}/content/upload` — proxy forwards
   body/headers as-is, so multipart passes through.
4. `validate_by_type` (source_validator_service.py:294-318) silently no-ops on
   unknown types — add terminal `else` raising ValueError.
5. `openapi.yaml` enum already `[url, pdf, text]`; `/content/upload` endpoint is
   undocumented — add it.
6. Docs drift: README:63,73 overstates (images/YouTube/topics); USER_GUIDE has
   no PDF row; GAP_ANALYSIS GAP-024 stale (PDF extraction done), FR-002 "PDF
   upload UI missing" fixed by this PR; env-config report:273 mentions YouTube.

## TDD checklist

### Backend (apps/api)
- [x] Test: `validate_by_type` with unsupported type (e.g. 'youtube') raises
      ValueError naming supported set → add terminal `else` (RED→GREEN)
- [x] Update model comment content_source.py:24-33 (supported vs reserved types)
- [x] Error messages in routers/content.py:409 + tasks/content_extraction.py:60
      reference supported list ['url', 'pdf', 'text']
- [x] openapi.yaml: document POST /episodes/{episode_id}/content/upload

### Frontend (apps/web)
- [x] Tests: page.test.tsx — PDF toggle renders file input; PDF submit posts
      FormData to /api/proxy/.../content/upload; oversize/wrong-type file shows
      validation error (RED)
- [x] validation.ts: add "pdf" to enum + superRefine (file required,
      application/pdf, ≤50MB)
- [x] page.tsx: PDF toggle button; file input (accept="application/pdf") with
      RHF error pattern; FormData submit path incl. auto_extract; replace :708
      hint with "Supports public HTTP/HTTPS article URLs" (GREEN)

### Docs
- [x] README.md:63,73 → websites, PDFs, plain text only
- [x] docs/USER_GUIDE.md: add PDF row to Supported Content Types
- [x] docs/GAP_ANALYSIS.md: GAP-024 closed; FR-002 complete
- [x] docs/environment-configuration-report-2025-11-11.md:273 drop YouTube

### Gates
- [x] pytest + jest + lint green; deslop; internal review + opencode/GLM review
- [x] PR, demo (agent-browser PDF upload flow), CI green, merge
