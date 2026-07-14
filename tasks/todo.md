# Tasks

## Active: Issue #317 — nginx upstream port drift (provision-ssl.sh vs deploy ports)

### Status of original CodeRabbit plan
- Phase 1 Task 1 (fix podcastfy.conf to 8005/3010): **already done** on main (conf already 8005/3010 with explanatory comment).
- Remaining work adapted below.

### Plan (approved autonomously — no architectural fork)
- [ ] RED: add `deployment/tests/test_port_alignment.py` asserting:
  - conf API upstream port == `${API_PORT:-…}` default in provision-ssl.sh
  - conf frontend proxy_pass port == `${FRONTEND_PORT:-…}` default in provision-ssl.sh
  - provision-ssl.sh contains sed substitution for both ports
  - bootstrap heredoc has no stale hardcoded 8001 upstream
- [ ] GREEN: provision-ssl.sh — add `API_PORT="${API_PORT:-8005}"`, `FRONTEND_PORT="${FRONTEND_PORT:-3010}"`, guarded sed substitutions after `cp` (mirror DOMAIN pattern), remove unused `upstream podcastfy_api { server 127.0.0.1:8001; }` from bootstrap heredoc (dead: bootstrap block never proxies)
- [ ] Docs: deployment/README.md ~252-256 — replace stale "(8001/3003) single-tenant example" caveat with the new default+override contract
- [ ] Quality gate: pytest deployment/tests, bash -n, third-party review (opencode pre-PR)
- [ ] PR → demo (Showboat, infra — no browser) → CI green → merge

Last shipped: #376 (composition downloads S3-backed snippets to the worker) via PR #396, merged 2026-07-13 (cba6c84).
