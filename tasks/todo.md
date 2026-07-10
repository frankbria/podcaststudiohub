# Issue #307 — CSP nonce (drop 'unsafe-inline' script-src) + real build gates

**Plan source**: self-authored (no plan comment on issue), verified against code 2026-07-09.
**Branch**: `fix/307-csp-nonce-and-build-gates`

## Why this shape

nginx cannot mint per-request nonces (no native module on the VPS), so the CSP for
HTML documents moves to Next.js middleware — the official Next 15 pattern
(nonce + `'strict-dynamic'`, `'unsafe-eval'` in dev only). nginx keeps every other
security header; its `/static/` block keeps a CSP with `script-src 'self'` (no
unsafe-inline). Hash-based CSP is unworkable: Next's hydration payload changes
every request.

**Gotcha that forced a middleware rewrite**: next-auth v4 `withAuth` early-returns
for the signIn page (`/login`), `/api/auth/*` and `/_next` — wrapped middleware
never runs there, so the login page would get **no CSP**. Replace `withAuth` with a
plain middleware: nonce-CSP for all matched pages + auth gate via `getToken`
(what withAuth uses internally) with the same `/login?callbackUrl=` redirect.

## Steps (TDD)

- [ ] 1. Branch off main.
- [ ] 2. RED — extend `apps/web/__tests__/middleware.test.ts`:
  - existing auth tests keep passing unchanged (redirect w/ callbackUrl; authed pass-through)
  - CSP response header present on protected AND public (`/login`) routes
  - `script-src` contains a base64 nonce + `'strict-dynamic'`, NOT `'unsafe-inline'`
  - `style-src` keeps `'unsafe-inline'` (Radix/shadcn inline style attrs)
  - media-src/connect-src keep both S3 hosts (episode audio streaming/download)
  - nonce differs across requests; `x-nonce` request header forwarded
- [ ] 3. RED — update `deployment/tests/test_nginx_config.py`:
  - server block no longer sets CSP (moved to app); other headers still asserted
  - `/static/` CSP has no `'unsafe-inline'` in script-src
  - drop/replace `test_csp_allows_s3_audio` (S3 allowance asserted in jest now)
- [ ] 4. GREEN — rewrite `apps/web/src/middleware.ts` (plain middleware, matcher
  `/((?!api|_next/static|_next/image|favicon.ico).*)` — no prefetch `missing`
  exclusions, preserving #222 auth-on-prefetch behavior).
- [ ] 5. GREEN — `apps/web/src/app/layout.tsx`: async, read `x-nonce` via
  `headers()`, pass `nonce` to the theme-flash inline script.
- [ ] 6. GREEN — `deployment/nginx/podcastfy.conf`: remove server-level CSP
  add_header (comment: owned by Next middleware); `/static/` CSP drops
  unsafe-inline from script-src.
- [ ] 7. `apps/web/next.config.mjs`: delete `eslint.ignoreDuringBuilds` +
  `typescript.ignoreBuildErrors` (lint + typecheck verified green locally; CI
  gates already blocking; server-side rebuild in deploy-dev.yml now also gated).
- [ ] 8. Verify: jest w/ coverage (≥80 gate), deployment pytest, `next build`
  (flags removed → build runs lint+types), lint, typecheck.
- [ ] 9. Deslop scan; quality gate incl. opencode (GLM) review pre-PR.
- [ ] 10. PR; demo: `next start` + curl -I → CSP header w/ nonce, no
  unsafe-inline in script-src; browser loads login/dashboard with zero CSP
  violations; build fails when a type error is injected (gate proof, reverted).
- [ ] 11. Post-PR opencode review comment; CI green; docs sync; merge.

## Risks

- Nonce CSP forces dynamic rendering of all pages — fine for an authed SaaS
  behind PM2 (`next start`); Playwright E2E runs prod mode, so a broken CSP
  fails E2E loudly.
- style-src keeps unsafe-inline deliberately (inline `style=` attrs everywhere
  in Radix); issue AC only requires script-src.
