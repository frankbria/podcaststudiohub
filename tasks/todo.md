# Issue #381 — [P4.4.1] Clearing optional podcast metadata fields does not persist

Plan source: self-authored (no plan comment on issue). Deferred from PR #380 finding S4.

## Design decision (autonomous — no fork)
JSON-merge-patch semantics (RFC 7386): an optional metadata key explicitly sent as
`null` — or as an empty/whitespace string — is **deleted** from the merged
`podcast_metadata`. Required keys (`show_title`, `author`, `description`) cannot be
cleared: explicit `null`/empty is rejected 422 at the schema layer **before** any DB
write (avoids committing broken metadata pre-regeneration). Frontend always sends the
five optional fields, `null` when the form value is empty.

## Steps
1. **Backend tests first** (`apps/api/tests/test_rss_feed.py`):
   - PUT with `category: null` deletes the key from stored metadata (and other keys survive)
   - PUT with `artwork_url: ""` deletes the key (empty string same as null)
   - PUT with `show_title: null` → 422, metadata unchanged
   - Existing omit-field merge behavior unchanged
2. **Backend impl**:
   - `apps/api/src/schemas/rss_feed.py`: `model_validator` on `PodcastMetadataUpdate`
     rejecting explicitly-set null/blank for required keys
   - `apps/api/src/routers/rss_feed.py`: merge loop — explicitly-set `None`/blank-string
     values pop the key; others overwrite
3. **Frontend test** (`apps/web/__tests__/app/distribution/page.test.tsx`):
   PUT body carries `category: null` (etc.) when the dialog fields are cleared
4. **Frontend impl** (`apps/web/src/app/(auth)/projects/[id]/distribution/page.tsx`):
   replace conditional spreads with always-send `field: value || null`;
   widen `RawPodcastMetadata` optional fields to `string | null`

## Acceptance criteria
- [x] Clearing an optional field (category/language/copyright/artwork_url/website_url) in the dialog removes it from `podcast_metadata` and the regenerated feed — demoed against real stack (API + real dialog), posted to PR #394
- [x] Required fields cannot be cleared (422, no partial write) — demoed
- [x] Setting/updating fields still merges as before — demoed
- [x] Backend + frontend tests green; lint green — full suites + CI green

## Status: SHIPPED 2026-07-13
Merged via PR #394 (squash, 362dfd0); issue #381 closed. All 12 CI checks green.
Demo with outcome evidence (real Postgres + S3 + real dialog) posted to the PR.
Reviews: opencode pre-PR (1 Minor + 2 Nits, addressed with tests), opencode post-PR
(no findings), CI review bot both rounds (no defects).
Rode along: (a) conftest RequestValidationError no-rollback fix; (b) user-approved
pip-audit ignore for PYSEC-2026-2562 (langchain-core SSRF, Low, podcastfy-capped —
no podcastfy release incl. 0.4.3 reaches the langchain-core 1.2.11 fix; unreachable
code path here; context posted on #363).
