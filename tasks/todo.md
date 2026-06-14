# Release-Readiness Plan — podcaststudiohub

**Audit date:** 2026-06-13 · **Verdict:** 🔴 NOT READY (9 blockers) · **Issues:** #204–#226 (23 total)

Generated from a multi-agent audit (10 reviewers + adversarial verification). Each issue
carries file:line evidence + acceptance criteria on GitHub. Titles are phase-tagged `[PX.Y]`
so issue order == work order.

> The **9 blockers** are #204, #205, #206, #207, #208, #209, #210, #211, #212 — they span
> Phases 1–3 (not every Phase 1/2 item is a blocker: #213, #214, #217 are high/medium correctness
> fixes, not release blockers). The release gate below requires Phases 1–3 done.

> ⚠️ **The core mirage:** the app "seems to work" only because the test suite **mocks the
> generation engine**. Against the pinned `podcastfy==0.4.1` (pip-installed in the venv — there
> is **no** `podcastfy/` engine in the repo; `podcast-generator/` is empty scaffolding),
> **every** generation call fails (`#204`). Fixing that + replacing mocked tests with a real
> end-to-end demo is the gate to "ready-with-caveats".

---

## Phase 1 — Stop the bleeding (urgent security, mostly independent)
- [x] **P1.1 #207** Rotate live AWS/OpenAI/ElevenLabs/Gemini/Transistor keys ✅ done 2026-06-14 (old AWS key deactivated; verified never committed to git; S3 object policy added)
      → **Frank rotates** (deactivate the flagged AWS access key — ID is in issue #207 — in IAM). Secret scanner ✅ done (see below).
- [ ] **P1.2 #205** JWT verification ignores `type` claim — verification/refresh tokens usable as access tokens
- [ ] **P1.3 #206** SSRF — content URLs + webhook targets fetched server-side, no private-IP/metadata block
- [ ] **P1.4 #212** Backend JWT exposed to browser JS (NextAuth session) + leaked in SSE `?token=` URL

## Phase 2 — Restore the core product (generation pipeline)
- [ ] **P2.1 #204** 🔴 `generate_podcast()` called with invalid kwargs → **every generation fails**. *Unblocks the rest of Phase 2.* Add an autospec/signature-asserting test; pin `podcastfy==0.4.1`.
- [ ] **P2.2 #213** `/regenerate` passes wrong positional args → guaranteed 500, leaves episode degraded
- [ ] **P2.3 #217** Episode `tts_model`/`conversation_config` never forwarded → always OpenAI TTS
- [ ] **P2.4 #214** No guard against re-submitting generation for an in-progress episode (race)
- [ ] **P2.5 #210** PDF/file input non-functional — no upload endpoint; extraction ignores S3 key *(needs StorageService + #204)*
- [ ] **P2.6 #211** Distribution subsystem unreachable + would publish blank episodes *(needs #204 producing real episodes + metadata)*

## Phase 3 — Deployment hardening (gate before any prod deploy)
- [ ] **P3.1 #208** nginx serves authenticated SaaS over plain HTTP — enable TLS + HSTS/CSP/security headers
- [ ] **P3.2 #209** Deploys as root, uvicorn bound `0.0.0.0` (bypasses nginx); reconcile 8000/8001 port mismatch
- [ ] **P3.3 #224** Harden CI/agentic workflows — issue-title shell injection, dispatch-input injection, SHA-pin actions

## Phase 4 — Correctness & authz mediums
- [ ] **P4.1 #215** Inconsistent S3 key layout — workflow-chain path drops `user-{id}/` tenant prefix *(after #204/#210)*
- [ ] **P4.2 #220** finalize task runs upload inline (no retry); SSE session leak; wrong status in `on_upload_complete`
- [ ] **P4.3 #216** Stripe webhook signature bypass when secret unset *(latent — Stripe currently unreachable)*
- [ ] **P4.4 #218** Invitation acceptance not bound to invited email; team tables lack RLS backstop
- [ ] **P4.5 #219** `expires_in` hardcoded 86400 but JWT expires in 30 min *(relates to #205)*
- [ ] **P4.6 #222** No server-side route protection (middleware) for the `(auth)` group — defense-in-depth
- [ ] **P4.7 #234** IP-pin outbound fetches to close the residual DNS-rebinding SSRF TOCTOU *(fast-follow to #206/P1.3, which is done; core SSRF already mitigated — this is defense-in-depth, not a release blocker)*

## Phase 5 — UX, tech-debt, docs
- [ ] **P5.1 #221** TTS "Save Configuration" creates broken ElevenLabs configs (no voice-ID input) *(do after #217)*
- [ ] **P5.2 #223** Adopt or delete the dead `api-client` layer; fix signup loading; minor UX
- [ ] **P5.3 #226** Replace hardcoded gray Tailwind colors with design tokens; minor robustness nits
- [ ] **P5.4 #225** Rewrite CLAUDE.md/README for the SaaS monorepo; fix broken refs & config drift *(do last so docs reflect fixes)*

---

## Cross-phase dependencies
- `#204` (P2.1) gates meaningful work/testing on `#213 #217 #210 #211 #214 #215`.
- `#221` (P5.1) is only meaningful once `#217` (P2.3) forwards TTS config.
- `#210` (P2.5) needs `StorageService.download_file` wired (already exists, unused).
- `#225` (P5.4) last — so docs describe the fixed system.
- `#234` (P4.7) depends on `#206` (P1.3, done) — IP-pinning hardening of the shipped SSRF guard.

## Secrets / secret-scanner status
- ✅ **gitleaks pre-commit hook installed** (`.pre-commit-config.yaml`, `pre-commit install` run). gitleaks
  passed on all tracked files (no committed secrets; the live keys are in gitignored `.env` only).
- ✅ **Rotated 2026-06-14** — all keys cycled, old AWS key deactivated; full-history scan confirmed
  the keys were never committed/pushed (precautionary rotation, not a leak); S3 object policy added (#207 closed).
- Recommend moving real secrets to a secret manager / CI secrets; keep placeholders on dev machines.

## Release gate (Definition of Done for "ready-with-caveats")
1. Phase 1 + Phase 2 complete and **verified by a real, non-mocked end-to-end generation demo**
   (URL → transcript → audio → S3 → playable episode).
2. Phase 3 complete: HTTPS in front, non-root deploy, hardened CI.
3. New tests exist for: generation kwargs (autospec), `/regenerate`, webhook signature, SSRF rejection,
   route protection — so green CI reflects a working product.
4. P4/P5 can trail into a fast-follow milestone if explicitly accepted as known caveats.

## Ops changes already made this session
- README server IP removed (commit `bf9e606`).
- gitleaks pre-commit secret scanner added.
- Issues #161 / #162 (agentic noise) closed as not planned.
- Disabled (reversible via `gh workflow enable "<name>"`): Community Response, Issue Triage,
  PR Review, and all 6 Repo Maintainer workflows. **Kept active:** Test Suite, Deploy to Development,
  Playwright E2E, Draft PDF, Claude Code (manual `@claude` helper).
- Helper scripts: `scripts/create_audit_issues.py`, `scripts/renumber_audit_issues.py`,
  `scripts/audit_issue_map.json`.
