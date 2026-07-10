# #306 — COMPLETE (PR #351 squash-merged 2026-07-09, issue closed)

**Plan source**: self-authored (no plan comment on issue), verified against code 2026-07-09.
**Branch**: `fix/issue-306-cve-alerting-dep-hardening`

## Verified facts
- `.github/dependabot.yml` has only `github-actions`; no pip/uv or npm ecosystems.
- passlib has **zero imports** anywhere (src/tests/alembic) — `auth_service.py` already uses direct `bcrypt`. passlib exists in pyproject only to supply bcrypt via its extra.
- python-jose used in exactly 2 source files (`src/utils/jwt.py`, `src/services/auth_service.py`) + 3 test files (jose→jwt import at 4 sites), all HS256 encode/decode — trivially PyJWT-shaped. python-jose 3.5.0 still hard-depends on `ecdsa` (won't-fix PYSEC-2026-1325), so a pip-audit gate can only pass by removing jose → **migrate to PyJWT** (issue offers this option).
- pip-audit on current uv.lock: 108 findings / ~35 packages (lock is stale). podcastfy 0.4.1 caret caps: `setuptools<76`, `wheel<0.45` block fixes → `[tool.uv]` overrides; `langchain<0.4`, `pytest<9` cap some fixes → documented `--ignore-vuln`s; litellm/requests/pymupdf/aiohttp/etc. fixes fit within caps → `uv lock --upgrade`.
- npm: apps/web has 2 high findings; root (playwright/concurrently devDeps) also fails `--audit-level=high`.
- CI = `.github/workflows/test.yml` with a `quality-gate` job aggregating results.

## Steps
- [x] Explore + author plan
- [x] Branch `fix/issue-306-cve-alerting-dep-hardening`
- [x] pyproject: `python-jose[cryptography]` → `pyjwt>=2.10.1`; `passlib[bcrypt]` → `bcrypt>=4.0`; `[tool.uv]` overrides `setuptools>=78.1.1`, `wheel>=0.46.2`
- [x] Migrate jose→PyJWT in 2 src + 3 test files; 1675 backend tests green
- [x] `uv lock --upgrade` (108 findings → 16; fastapi 0.139/starlette 1.3.1; typer needed reinstall — corrupted wheel extract)
- [x] pip-audit gate green via `apps/api/scripts/security-audit.sh` (17 documented ignores, all podcastfy-capped: litellm needs openai>=2.20 vs podcastfy openai<2)
- [x] `npm audit fix` — workspace root lockfile covers apps/web; high-gate green both; web typecheck + 331 jest green
- [x] test.yml `security-audit` job wired into quality-gate; dep files added to push paths
- [x] dependabot.yml: `uv` (/apps/api) + `npm` (/) — npm workspaces mean root covers web
- [x] pytest.ini: ignore google.generativeai EOL FutureWarning ([\s\S]* — message starts with newline)
- [x] Deslop + opencode pre-PR review (approve; watch-items: dependabot `uv` ecosystem recognition, first real Actions run of the gate)
- [x] PR #351 → post-PR review (approve) → demo (caught CI JWT-key-length landmine, fixed) → CI green incl. new security-audit job → docs sync (.env.example 32-char note) → squash-merged

## Acceptance criteria (issue #306)
- [ ] pip + npm Dependabot ecosystems added
- [ ] CI pip-audit / `npm audit --audit-level=high` gate
- [ ] python-jose floor ≥3.4.0 **or migrate to PyJWT** → migrating to PyJWT (kills ecdsa too)
- [ ] Password hashing on pwdlib/direct bcrypt → already direct bcrypt; drop passlib, declare bcrypt
- [ ] uv overrides so security transitives float independent of podcastfy pin

---

# #305 — COMPLETE (PR #350 squash-merged 2026-07-09, issue closed)
(archived — see git history for details)
