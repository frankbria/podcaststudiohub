# #389 — [P4.3.5] Regenerate endpoint hardcodes enable_distribution=False

Status: SHIPPED — merged 2026-07-13 via PR #392 (squash, 8ca582a); issue #389 closed.
All gates green: backend CI 1811 passed (full suite locally too), ruff clean, 12/12 CI
checks incl. review bot (no defects). Demo posted to PR with outcome evidence against
real API + Postgres + Redis: decoded the queued Celery message from the
`podcast_generation` Redis queue showing `enable_distribution: true` + webhook
platforms with the flag, and both flags false by default. Reviews: opencode (GLM)
APPROVE pre-PR and post-PR (posted to PR); two advisory test-gap notes triaged —
feature-flag-off negative test added, composition twins declined (identical
delegation path already asserted).

## What shipped
`/generation/episodes/{id}/regenerate` now accepts `enable_composition` /
`enable_distribution` Query params (defaults `False`, mirroring `/generate`) and
passes them through the keyword-arg delegation (#213 guard kept). Default
`enable_distribution=true` on regenerate was considered and rejected for symmetry
with `/generate` — callers opt in explicitly, as the web generate action does (#388).

## Known limitation (documented in PR, no issue filed)
The web UI still has no regenerate call; this makes distribution callable on
regenerate via the API (the issue's minimum bar). A web regenerate button would be
a separate feature request.
