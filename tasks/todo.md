# Issue #491 — Dev VPS serves two CSP headers (nginx config on the box predates #307)

Plan source: self-authored (issue has a definition of done, no plan comment).

## Diagnosis (verified 2026-09-16)
- `curl -sI https://dev.podcaststudiohub.me/login | grep -ci content-security-policy` → 2
- `/etc/nginx/sites-available/podcastfy` on the box is dated 2026-07-06 (pre-#307, owned by `ubuntu`).
  Diff vs `deployment/nginx/podcastfy.conf`: stale server-level CSP with `'unsafe-inline'`,
  stale `/static/` CSP, missing `/ready` location.
- Root-owned clone `/root/podcaststudiohub` exists (README "How the box gets deployment assets").

## Steps
1. [ ] Test first: `deployment/tests/test_nginx_drift.py` — script exists/executable/`set -euo pipefail`,
       diffs `/etc/nginx/sites-available/podcastfy`, mirrors provision-ssl.sh DOMAIN/API_PORT/FRONTEND_PORT
       substitutions, workflow runs it after the Health Check; functional run with an `ssh` shim
       (in-sync → exit 0, drifted → non-zero + diff on stdout).
2. [ ] `deployment/scripts/check-nginx-drift.sh` — runner-side: `ssh cat` the live site file, `diff -u`
       against the committed conf rendered with the same substitutions provision-ssl.sh applies.
3. [ ] `.github/workflows/deploy-dev.yml` — step "Assert nginx config matches repo" after Health Check
       (post-deploy so a drift goes red without blocking security deploys).
4. [ ] `deployment/README.md` — "To update the Nginx config" section: sync from the root clone, note the gate.
5. [ ] Ops (root on the box): `git -C /root/podcaststudiohub pull`, copy conf → sites-available, `nginx -t`,
       `systemctl reload nginx`. Must land before merge or the first deploy goes red.

## Acceptance criteria (issue DoD)
- [ ] Box config re-synced from `deployment/nginx/podcastfy.conf`; document CSP only from the middleware
- [ ] `curl -sI https://dev.podcaststudiohub.me/login | grep -ci content-security-policy` → 1
- [ ] Remaining header is the nonce policy; `/static/` still carries its own strict CSP
- [ ] Deploy step asserts live config == committed config and fails loudly on drift (nginx stays operator-installed)

## Autonomous decisions
- Gate placement: after Health Check (deploy completes, run goes red on drift). Pre-deploy would block
  security bumps on a 1-minute operator action.
- Drift check is a runner-side script (nothing new rsynced to the box; nothing root-run).
