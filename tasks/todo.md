# [P0.1] #481 — Signup page crashes on a Pydantic 422

## Root cause (confirmed, not hypothesised)

1. `UserRegister.full_name` is required, `min_length=1` (`apps/api/src/schemas/auth.py:18`).
2. `tests/e2e/specs/01-auth.spec.ts:42` ("should show error for existing email") fills only
   email + password, so the form posts `full_name: ""` → Pydantic rejects it with **422**, whose
   `detail` is an **array** of `{msg, loc, type}`.
3. `apps/web/src/app/signup/page.tsx:33` does `setError(data.detail || "Registration failed")`,
   putting that array into a `string` state (untyped — `response.json()` is `any`, so tsc misses it).
4. Line 102 renders `{error}` → React throws *"Objects are not valid as a React child"*.
5. `apps/web/src` has **no error boundary at all**, so the throw escapes to Next's built-in root
   handler and the route dies.

The 422 is deterministic. What varies is only which crash surface appears — and the assertion
`text=/error|already|exist/i` matches Next's own "Application **error**…" text, so the test
*passed* whenever that page rendered. It never once asserted a real validation message.

With `full_name` filled, `create_user` returns **400 + `detail: "Email already registered"`**
(a string) — the duplicate-email path the test was named for.

## Plan

### Step 1 — Fix the crash at its root (TDD)
- RED: `apps/web/__tests__/app/signup/page.test.tsx` — add a case mocking an **array-shaped**
  `detail` (`[{msg: "String should have at least 1 character", loc: [...], type: "..."}]`);
  assert the joined message renders and the component does not throw.
- GREEN: route line 33 through the existing `extractApiErrorDetail(body, fallback)` from
  `apps/web/src/lib/api-error.ts` — the helper already handles both FastAPI shapes and is already
  used by `AppleConnectDialog` / `WebhookConnectDialog`.
- Files: `src/app/signup/page.tsx`, `__tests__/app/signup/page.test.tsx`

### Step 2 — Same defect class, remaining callers
`projects/[id]/distribution/page.tsx:144` and `:187` interpolate `${body.detail}` into a toast →
`[object Object]` on a 422. Not fatal, same root cause; fixing only the caller the ticket names
leaves siblings broken.
- Route both through `extractApiErrorDetail`. Add/extend tests.
- Files: `src/app/(auth)/projects/[id]/distribution/page.tsx` + its test
- (`episodes/[id]/page.tsx:427` is already guarded with a `typeof detail === "string"` check —
  leave it.)

### Step 3 — Stop a render throw from killing the route
- Add `apps/web/src/app/error.tsx` (Next's native route error boundary) so any client render
  throw degrades to recoverable in-app UI with a reset action instead of a dead page.
- Scope: ONE root boundary. No per-route boundaries.
- Files: `src/app/error.tsx`, `__tests__/app/error.test.tsx`

### Step 4 — Make the E2E test assert the right thing (issue criteria 1 & 2)
- Fill the full-name field so the request is a genuine duplicate-email submission (400 + string
  detail) rather than a request-shape rejection.
- Assert against `#signup-error` specifically, so a dead page and a validation message can no
  longer be confused.
- Files: `tests/e2e/specs/01-auth.spec.ts`

## Acceptance criteria (from the issue's "Suggested next steps")

- [ ] 1. Test asserts a specific error element, not a broad text regex — a dead page and a
      validation message are distinguishable.
- [ ] 2. The test exercises the precise duplicate-email path (400 + string detail), not a
      validation rejection it was passing on by accident.
- [ ] 3. A 422 on `/auth/register` can no longer take the signup page down.

## Autonomous decisions (no architectural fork)

- **Reuse `extractApiErrorDetail`** rather than adding a guard per call site — one shared helper
  already exists and already encodes this exact contract.
- **One root `error.tsx`**, not a boundary per route — smallest change that closes criterion 3.
- **Keep the pre-seeded E2E user** rather than making the test self-seeding: the issue offered
  either, and self-seeding would add a registration call against a rate limit the spec is
  explicitly designed to avoid.
- **No backend change.** A 422 for a malformed body is correct REST; the defect is that the
  frontend cannot render it.
