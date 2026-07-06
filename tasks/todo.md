# #302 tail — restore green E2E signal (un-fixme'd specs must actually run)

Context: #338 delivered the infra; #340 un-fixme'd the journey/isolation specs. But:
- Staging nginx (installed from repo config during 07-01 VPS rebuild) 500s on /login:
  `try_files $uri $uri/ /index.html` + `root` inside the `location /` proxy block →
  internal redirection cycle (confirmed in /opt/podcaststudiohub/logs/frontend-error.log).
- The #340 deploy failed at ssh-keyscan (transient fail2ban ban, now expired) → dev
  still runs pre-#340 code, so project/episode creation is still broken there.

## Steps
- [ ] 1. Live-fix staging nginx (backup, drop root/try_files from proxy location, nginx -t, reload); verify /login 200
- [ ] 2. Re-run failed deploy run 28540506708 → dev gets #340 code; verify project create works
- [ ] 3. Branch fix/302-e2e-green-tail:
      - deployment/nginx/podcastfy.conf: remove root/try_files from proxy location; port 3003→3010
      - tests/e2e/README.md: drop stale "BLOCKED on #337" section (specs are re-enabled)
      - playwright-tests.yml thresholds: tighten from observed green-run numbers
- [ ] 4. Re-run Playwright on main → confirm re-enabled specs pass against fixed dev
- [ ] 5. Quality gate (lint, third-party review), PR with Known Limitations
- [ ] 6. Demo evidence (CI signal numbers + curl proof), CI green, merge, close #302
