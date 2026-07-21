# Issue #324 — Docs drift & repo hygiene (P6.1)

Branch: `chore/324-docs-repo-hygiene`. All claims verified against repo state before acting.

## Plan (no architectural fork — approved autonomously)

- [ ] **README.md** — fix 3 defects
  - [ ] `:57` "Systemd for service management" → "PM2 for process management" (truth: deployment/README uses PM2; systemd only resurrects PM2 on boot)
  - [ ] `:277` `data/` labeled "(gitignored)" → clarify committed sample audio is tracked; only new runtime output is ignored
  - [ ] `:282` `deploy.yml` → `deploy-dev.yml` (actual workflow filename)
- [ ] **docs/ broken Sphinx tooling** — remove (no `source/` or `conf.py` exist): `Makefile`, `make.bat`, `generate_api_docs.py`, `requirements.txt`
- [ ] **docs/ stale/alarming agent reports** — delete (git history preserves): `GAP_ANALYSIS.md`, `environment-configuration-report-2025-11-11.md`, `env_inventory.md`. Keep `USER_GUIDE.md`, `missing-credentials-guide.md` (current).
- [ ] **.apm/ (32 files) + podcast-generator/ (19 files)** — `git rm -r` both, add to `.gitignore` (confusing second project roots; `.claude/commands/apm-*.md` regenerate `.apm/` so removal is safe)
- [ ] **apps/api/src/middleware/auth.py** — remove stale "Task 2.4" comment (:148); fix `get_active_user` docstring (claims "verified" but only checks active) + delete dead commented email-verification block
- [ ] **apps/api/src/services/auth_service.py:87** — drop "in Task 2.4" from comment
- [ ] **apps/api/src/services/content_extraction_service.py:5** — drop "from Task 2.7" from docstring
- [ ] **apps/api/scripts/test_credentials.py** — rename → `check_credentials.py` (fixes pytest-collection hazard: `test_`-prefixed funcs; deps already lazily imported so no import-time break)

## Verify
- [ ] `pytest tests/` collects cleanly, app imports
- [ ] No dangling references to deleted files
- [ ] ruff clean on touched Python
