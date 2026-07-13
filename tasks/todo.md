# #391 — [P4.3.6] RSS `<enclosure>` URLs embed private S3 URLs

Status: SHIPPED — merged 2026-07-13 via PR #393 (squash, 0b68620); issue #391 closed.
All gates green: 12/12 CI checks (backend 1818 passed), ruff clean, review bot 0 findings
across both synchronize rounds. Demo posted to PR with outcome evidence against the real
S3 bucket: real upload → feed XML shows API enclosure URL (no raw S3), HEAD+GET → 302 to
presigned URL, downloaded bytes identical, Range served, random UUIDs → 404, two requests
→ distinct signatures. Demo caught a real bug pre-merge: 405 on HEAD (FastAPI doesn't add
HEAD to GET routes; platforms HEAD enclosures) — fixed with methods=["GET","HEAD"] + test.

## What shipped
Enclosures now emit `{API_PUBLIC_BASE_URL}/feeds/episodes/{user_id}/{episode_id}/audio.mp3`;
the public endpoint 302-redirects to a per-request presigned URL (1h, Cache-Control:
no-store), 404s via a real S3 HEAD check, and derives the key from the URL
(`build_podcast_s3_key`, #215) — no DB read, episodes is FORCE RLS (#385 precedent).
Episodes without `s3_key` keep the legacy `s3_url` fallback. The issue's sketched
project_id path was underivable; URL carries user_id (already exposed in old raw S3 URLs).

## Review triage of note
opencode (GLM) pre-PR Major "remove file_exists (TOCTOU)" was declined as factually wrong:
presigning is local computation that never fails on a missing key, so the HEAD check is
the only real 404 path. Post-PR review + both bot rounds: APPROVE / 0 findings.

## Also in this PR (unrelated, blocked CI)
PYSEC-2026-2193 (langchain-core 0.3.86, fix only in 1.2.22) added to the pip-audit ignore
list — structurally capped by podcastfy 0.4.1's langchain<0.4 pin; noted on #363.
