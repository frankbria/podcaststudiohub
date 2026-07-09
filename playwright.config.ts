import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright configuration for PodcastStudioHub E2E tests
 * See https://playwright.dev/docs/test-configuration
 */

const baseURL = process.env.BASE_URL || 'https://dev.podcaststudiohub.me';
// When BASE_URL points at localhost the suite runs against a PR-built local
// stack (see #341): Playwright boots the API + web servers itself via
// `webServer` below, and CI provides Postgres/Redis as job services. Any
// other BASE_URL (e.g. the deployed dev host) is treated as an already-running
// remote target and no local servers are launched.
const isLocalStack = /^https?:\/\/(localhost|127\.0\.0\.1)(:|\/|$)/.test(baseURL);
const apiURL = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8200';
const webPort = new URL(baseURL).port || '3200';

export default defineConfig({
  testDir: './tests/e2e',

  /* Register shared test user and save auth state before all tests */
  globalSetup: './tests/e2e/global-setup.ts',

  /* Run tests in files in parallel */
  fullyParallel: true,

  /* Fail the build on CI if you accidentally left test.only in the source code. */
  forbidOnly: !!process.env.CI,

  /* Retry on CI only */
  retries: process.env.CI ? 2 : 0,

  /* Opt out of parallel tests on CI. */
  workers: process.env.CI ? 1 : undefined,

  /* Reporter to use */
  reporter: [
    ['html'],
    ['list'],
    // Machine-readable report consumed by the CI skip-count gate (see
    // .github/workflows/playwright-tests.yml). Keeps an all-skipped suite from
    // ever reporting green again.
    ['json', { outputFile: 'playwright-report/results.json' }],
    process.env.CI ? ['github'] : ['list'],
  ],

  /* Shared settings for all the projects below */
  use: {
    /* Base URL to use in actions like `await page.goto('/')`. */
    baseURL,

    /* Pre-authenticated session from global-setup */
    storageState: 'tests/e2e/.auth/user.json',

    /* Collect trace when retrying the failed test */
    trace: 'on-first-retry',

    /* Screenshot on failure */
    screenshot: 'only-on-failure',

    /* Video on failure */
    video: 'retain-on-failure',
  },

  /* Configure projects for major browsers */
  /* NOTE: Temporarily reduced to Chromium-only while E2E stability is fixed (see #94) */
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },

    // Disabled until E2E tests are stable — see issue #94
    // {
    //   name: 'firefox',
    //   use: { ...devices['Desktop Firefox'] },
    // },
    //
    // {
    //   name: 'webkit',
    //   use: { ...devices['Desktop Safari'] },
    // },
    //
    // {
    //   name: 'Mobile Chrome',
    //   use: { ...devices['Pixel 5'] },
    // },
    // {
    //   name: 'Mobile Safari',
    //   use: { ...devices['iPhone 12'] },
    // },
  ],

  /* PR-built local stack (#341): boot API + web when BASE_URL is localhost.
   * Prereqs: `uv sync` in apps/api (+ migrated Postgres, Redis) and
   * `npm run build:web`. Both processes inherit env (DATABASE_URL, JWT keys,
   * NEXT_PUBLIC_API_URL, …) from the invoking shell / CI step. */
  webServer: isLocalStack
    ? [
        {
          command: `uv run uvicorn src.main:app --host 127.0.0.1 --port ${new URL(apiURL).port || '8200'}`,
          cwd: 'apps/api',
          url: `${apiURL}/health`,
          reuseExistingServer: !process.env.CI,
          timeout: 120_000,
          stdout: 'pipe',
          stderr: 'pipe',
        },
        {
          command: 'npm start',
          cwd: 'apps/web',
          url: baseURL,
          reuseExistingServer: !process.env.CI,
          timeout: 120_000,
          stdout: 'pipe',
          stderr: 'pipe',
          env: { PORT: webPort },
        },
      ]
    : undefined,
});
