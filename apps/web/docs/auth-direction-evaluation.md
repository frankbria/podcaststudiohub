# Auth direction: Auth.js v5 vs Better Auth vs staying on next-auth v4

**Decision (2026-09-08, issue #442): stay on `next-auth` v4. Re-evaluate only when a trigger below
fires.** Recorded here rather than only in the issue because a closed issue is easy to lose and
this question will be asked again.

## What next-auth actually does in this app

This is the fact that decides it, and it is easy to miss: **next-auth is a thin shim here.**

FastAPI owns identity completely — `/auth/register`, `/auth/login`, `/auth/me`, account deletion,
`/auth/verify-email`, `/auth/resend-verification-email`, password hashing and strength rules,
`tenant_id`, RLS context, and registration rate limiting.

next-auth owns exactly three things:

| Thing | Where |
|---|---|
| An httpOnly cookie holding the backend's JWT | `src/lib/auth.ts` |
| `useSession()` for "who am I" display | 8 components |
| `getToken()` for middleware route-gating and `/api/proxy` token injection | `src/middleware.ts`, `src/app/api/proxy/[...path]/route.ts` |

That is ~100 lines of config plus a type augmentation. None of the library's database, adapter, or
provider machinery is used. **Any comparison that weighs adapters, schemas, or provider ecosystems
is weighing things this app does not use** — which is why the usual "Better Auth beats Auth.js"
advice does not transfer directly.

## The original driver is gone

#442 was opened because `npm audit --audit-level=high` could not go green on v4. #445 bumped
next-auth to 4.24.15, which cleared all four advisories and emptied the JS allowlist. There is no
security forcing function left.

## v4 is supported on this stack and still maintained

`next-auth@4.24.15` peer dependencies:

```json
"next":  "^12.2.5 || ^13 || ^14 || ^15 || ^16",
"react": "^17.0.2 || ^18 || ^19"
```

It formally supports Next 16 and React 19 — the versions this repo runs. Release cadence is real
maintenance, not abandonment: 4.24.12 (2025-10-27), 4.24.13 (2025-10-29), 4.24.14 (2026-04-14),
4.24.15 (2026-07-20).

## Options considered

| Option | Verdict |
|---|---|
| **Auth.js v5** | **Ruled out.** v5 has never left the `beta` dist-tag — `latest` is 4.24.15, `beta` is 5.0.0-beta.32, after 3+ years. Auth.js is now maintained by the Better Auth team in security-patch mode, and its own guidance points new projects at Better Auth. The only option that pays a real migration cost to arrive somewhere worse. |
| **Better Auth** | **The right destination, but not a swap.** It requires a database it owns; delegating credential verification to an external API is unsupported in stable releases (better-auth #4771, discussions #6767 / #6410), and the stateless mode that would allow it is beta/canary and not production-recommended. Its peer deps (`pg`, `mysql2`, `prisma`, `drizzle-orm`, `mongodb`, `better-sqlite3`) confirm the design intent. Adopting it means moving the identity boundary — Better Auth owns `users`, FastAPI verifies — which touches multi-tenant RLS, the highest-risk code in the app. |
| **Drop the library** | **Ruled out.** ~100–150 lines to replace, but those lines are cookie encryption and CSRF, which is where auth implementations go wrong. Not worth removing one dependency. |
| **Stay on v4** | **Chosen.** Zero cost, no security exposure, formally supported. |

## Re-evaluation triggers

Event-based, not calendar-based. Re-open #442 when **either** fires:

1. **We want user-facing social login, SSO, 2FA, or passkeys.** None exists today — the only OAuth
   in the codebase is Spotify for *distribution* (`apps/api/src/services/spotify_service.py`),
   unrelated to user login. Note that adding an OAuth provider also makes GHSA-x445-f3h2-j279
   (cross-provider check-cookie confusion) live, which the `CredentialsProvider`-only setup
   currently dodges.
2. **v4 stops declaring Next support** — a future Next major absent from its peer range — or a new
   advisory lands with no v4 fix.

When a trigger fires the direction is **Better Auth as the identity owner**, scoped as a project
that moves the identity boundary with an explicit plan for `tenant_id` and RLS. Do not route
through Auth.js v5 on the way.
