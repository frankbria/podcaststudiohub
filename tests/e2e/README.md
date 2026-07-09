# PodcastStudioHub E2E Test Suite

Automated end-to-end tests using Playwright.

## Test Coverage

The repo contains a large speculative spec set, but **most of it is `fixme`'d** —
many specs were written against UI that didn't exist yet, so they were disabled.
A disabled (`test.describe.fixme` / `test.fixme`) block is reported by Playwright
as *skipped*, not passed. The CI `notify` job and a dedicated **skip-count gate**
(`.github/workflows/playwright-tests.yml`) surface skip counts and fail the build
if real coverage drops, so a mostly-skipped suite can no longer report green.

### Active (executing) coverage

- **`01-auth.spec.ts`** — Authentication: signup, login, session persistence,
  route protection (logged-out → `/login`), navigation links.
- **`02-projects.spec.ts → Project Access Control (isolation)`** — User B
  cannot open User A's project (two independent sessions, negative assertions).
- **`03-episodes.spec.ts → Episode Access Control (isolation)`** — the same
  two-session pattern for episodes.
- **`10-integration.spec.ts → Complete User Journey`** — the headline path:
  signup → project → episode → content → ready-to-generate → logout.
- **`10-integration.spec.ts → Concurrent User Workflow`** — dashboard listing
  and direct-URL data isolation between two independent users.

The isolation/journey specs were un-`fixme`'d once the web↔API contract fix
(#337, PR #340) landed. This active set is the CI gate's `MIN_PASSED` floor.

### Disabled (`fixme`) — not yet verified against the current UI

`04-content`, `05-generation`, `06-navigation`, `07-responsive`,
`08-performance`, `09-accessibility`, the CRUD/edit/delete/nav sub-suites of
`02`/`03`, and the heavier `10-integration` workflows remain `fixme`'d. Live
generation + download (`10-integration → Generation and Download`) is `fixme`'d
because it depends on the generation pipeline work tracked in #313/#314 and is
too slow / external-API dependent to gate every PR. Un-`fixme` these as the
corresponding UI is verified, and raise `MIN_PASSED` in the CI gate accordingly.

### Two-session isolation

Multi-tenant tests use two genuinely independent authenticated contexts. **User A**
is the shared `storageState` (`.auth/user.json`); **User B** is a second tenant
provisioned once by `global-setup` (`.auth/user-b.json`, a deterministic
plus-addressed account derived from `E2E_TEST_EMAIL`). Provisioning User B once —
rather than signing up a fresh user per test — keeps the suite within the dev
registration rate limit (3/hr/IP).

## Execution model (#341)

- **PRs and pushes** run against a **PR-built local stack**: when `BASE_URL`
  points at localhost, `playwright.config.ts` boots the API (uvicorn) and the
  built web app (`next start`) via Playwright's `webServer`, with Postgres/Redis
  provided as CI job services. A PR therefore validates **its own code**, and a
  dev-host outage can no longer fail (or falsely pass) a PR.
- **Dev-smoke** is the optional `workflow_dispatch` path of
  `.github/workflows/playwright-tests.yml`: it targets the deployed
  `https://dev.podcaststudiohub.me` and is **skipped with a warning** (not
  failed) when dev's `/api/health` is unreachable.
- `global-setup` preflights the API health endpoint so an unreachable/unhealthy
  target fails with an explicit environment error instead of an opaque
  `input[type="email"]` timeout.

## Running Tests

### Run against a local PR-built stack
```bash
# Prereqs: Postgres + Redis running, `uv sync` done in apps/api, and a web build:
NEXT_PUBLIC_API_URL=http://localhost:8200 npm run build:web

# One-time DB setup — the API MUST connect as the RLS-subject app role
# (podcastfy_app), not the bootstrap superuser: superusers bypass RLS even
# under FORCE ROW LEVEL SECURITY, so the isolation specs would (correctly)
# fail with cross-tenant reads. Migrations run as the BYPASSRLS owner:
#   CREATE ROLE podcastfy_user LOGIN PASSWORD 'postgres' NOSUPERUSER NOCREATEDB NOCREATEROLE BYPASSRLS;
#   CREATE ROLE podcastfy_app  LOGIN PASSWORD 'postgres' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
#   CREATE DATABASE podcastfy_e2e OWNER podcastfy_user;
# then (from apps/api):
#   MIGRATION_DATABASE_URL=postgresql+asyncpg://podcastfy_user:postgres@localhost:5432/podcastfy_e2e \
#   DATABASE_URL=postgresql+asyncpg://podcastfy_app:postgres@localhost:5432/podcastfy_e2e \
#   ENCRYPTION_KEY=test-encryption-key-for-ci-00000 JWT_SECRET_KEY=test-jwt-secret-for-ci \
#   uv run alembic upgrade head

BASE_URL=http://localhost:3200 API_URL=http://localhost:8200 \
NEXT_PUBLIC_API_URL=http://localhost:8200 \
DATABASE_URL=postgresql+asyncpg://podcastfy_app:postgres@localhost:5432/podcastfy_e2e \
ENVIRONMENT=development ENCRYPTION_KEY=test-encryption-key-for-ci-00000 \
JWT_SECRET_KEY=test-jwt-secret-for-ci NEXTAUTH_SECRET=test-nextauth-secret-for-ci \
NEXTAUTH_URL=http://localhost:3200 CORS_ORIGINS='["http://localhost:3200"]' \
RATE_LIMIT_ENABLED=false BILLING_ENFORCEMENT_ENABLED=false \
E2E_TEST_EMAIL=e2e-ci@example.com E2E_TEST_PASSWORD='E2e-ci-Passw0rd!' \
npx playwright test
```
Playwright starts uvicorn (:8200) and `next start` (:3200) itself and reuses
already-running servers outside CI.

### Run all tests (against the default remote target)
```bash
npx playwright test
```

### Run specific test file
```bash
npx playwright test tests/e2e/specs/01-auth.spec.ts
```

### Run tests in headed mode (see browser)
```bash
npx playwright test --headed
```

### Run tests in specific browser
```bash
npx playwright test --project=chromium
npx playwright test --project=firefox
npx playwright test --project=webkit
```

### Run tests in debug mode
```bash
npx playwright test --debug
```

### View test report
```bash
npx playwright show-report
```

## Test Structure

```
tests/e2e/
├── fixtures/          # Test fixtures and mock data
├── utils/             # Helper functions
│   ├── auth-helpers.ts
│   ├── project-helpers.ts
│   └── episode-helpers.ts
├── specs/             # Test specifications
│   ├── 01-auth.spec.ts
│   ├── 02-projects.spec.ts
│   └── ...
└── README.md
```

## Environment Variables

Set `BASE_URL` to test against different environments:

```bash
# Test against development
BASE_URL=https://dev.podcaststudiohub.me npx playwright test

# Test against local
BASE_URL=http://localhost:3000 npx playwright test

# Test against production
BASE_URL=https://podcaststudiohub.me npx playwright test
```

## CI/CD Integration

Tests run automatically on:
- Pull requests to main/develop — against the PR-built local stack
- Pushes to main/develop — against the stack built from the merged code
- Manual workflow dispatch — dev-smoke against the deployed dev host
  (non-blocking: skipped when dev is down)

`.github/workflows/playwright-tests.yml` is the **single authoritative E2E
signal** (with the skip-count gate); the old always-green `test-e2e` job in
`test.yml` was removed (#341).

## Writing New Tests

1. Create new spec file in `tests/e2e/specs/`
2. Use helper functions from `utils/` directory
3. Follow existing test patterns
4. Add descriptive test names
5. Use page object pattern for complex pages

Example:
```typescript
import { test, expect } from '@playwright/test';
import { signUpAndLogin } from '../utils/auth-helpers';

test.describe('Feature Name', () => {
  test('should do something', async ({ page }) => {
    const user = await signUpAndLogin(page);

    // Test code here
    await expect(page).toHaveURL(/\/dashboard/);
  });
});
```

## Test Utilities

### Authentication
- `generateTestUser()` - Create unique test user
- `signUp(page, user)` - Register new user
- `login(page, email, password)` - Login existing user
- `logout(page)` - Logout via the MainNav user-menu dropdown (`User menu` → `Logout`)
- `signUpAndLogin(page)` - Combined signup and login
- `createUserBContext(browser)` - Open a second independent context as User B (for isolation tests)

### Projects
- `createProject(page, data)` - Create a project via the dashboard dialog; returns its id (navigates via the `Open project: <title>` card)
- `navigateToProject(page, id)` - Go to project page
- `verifyProjectExists(page, title)` - Check project in dashboard

### Episodes
- `createEpisode(page, projectId, data)` - Create an episode (`#episode-title`); returns its id
- `addContentSource(page, episodeId, source)` - Add URL/text content via the URL/Text toggle + `#content-url`/`#content-text`
- `generatePodcast(page, episodeId)` - Click "Generate Podcast", assert status `Status: queued`
- `waitForGeneration(page, episodeId)` - Wait for the `Status: complete` badge
- `verifyAudioPlayer(page)` - Assert the native `<audio controls>` element and the `Download MP3` button

## Best Practices

1. **Use descriptive test names** - Test names should describe what they test
2. **Keep tests isolated** - Each test should be independent
3. **Use helper functions** - Reuse common operations
4. **Set appropriate timeouts** - For long operations like generation
5. **Clean up after tests** - Delete test data when possible
6. **Use test fixtures** - For shared setup/teardown
7. **Screenshot on failure** - Already configured
8. **Record video on failure** - Already configured

## Debugging Failed Tests

1. Check test report: `npx playwright show-report`
2. View screenshots in `test-results/`
3. Watch failure videos in `test-results/`
4. Run in headed mode to see browser
5. Use `await page.pause()` to debug interactively

## Performance Considerations

- Tests run in parallel by default
- Use `test.describe.serial()` for dependent tests
- Set timeout for long-running tests:
  ```typescript
  test('long test', async ({ page }) => {
    test.setTimeout(300000); // 5 minutes
    // ...
  });
  ```

## Accessibility Testing

Use `@axe-core/playwright` for automated accessibility checks:

```typescript
import { injectAxe, checkA11y } from 'axe-playwright';

test('should be accessible', async ({ page }) => {
  await page.goto('/dashboard');
  await injectAxe(page);
  await checkA11y(page);
});
```

## Visual Regression Testing

Use `@percy/playwright` for visual comparisons:

```typescript
import percySnapshot from '@percy/playwright';

test('visual test', async ({ page }) => {
  await page.goto('/dashboard');
  await percySnapshot(page, 'Dashboard');
});
```
