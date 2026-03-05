import { chromium, type FullConfig } from '@playwright/test';
import { mkdirSync } from 'fs';
import { dirname } from 'path';

const AUTH_STATE_PATH = 'tests/e2e/.auth/user.json';

async function globalSetup(config: FullConfig) {
  const E2E_TEST_EMAIL = process.env.E2E_TEST_EMAIL;
  const E2E_TEST_PASSWORD = process.env.E2E_TEST_PASSWORD;

  if (!E2E_TEST_EMAIL || !E2E_TEST_PASSWORD) {
    throw new Error(
      'E2E_TEST_EMAIL and E2E_TEST_PASSWORD must be set. ' +
      'In CI these come from GitHub Secrets. Locally, add them to a .env file or export them.'
    );
  }

  mkdirSync(dirname(AUTH_STATE_PATH), { recursive: true });

  const baseURL = config.projects[0].use.baseURL || 'https://dev.podcaststudiohub.me';
  const apiURL = process.env.NEXT_PUBLIC_API_URL || `${baseURL}/api`;

  // Step 1: Register the shared test user (idempotent — ignore if exists)
  try {
    const registerResponse = await fetch(`${apiURL}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: E2E_TEST_EMAIL,
        password: E2E_TEST_PASSWORD,
        full_name: 'E2E Test User',
      }),
    });

    if (registerResponse.ok) {
      console.log('[global-setup] Shared test user registered');
    } else if (registerResponse.status === 400 || registerResponse.status === 409) {
      console.log('[global-setup] Shared test user already exists');
    } else {
      const body = await registerResponse.text();
      console.warn(`[global-setup] Registration returned ${registerResponse.status}: ${body}`);
    }
  } catch (err) {
    console.warn(`[global-setup] Registration request failed: ${err}`);
  }

  // Step 2: Log in via the browser to get the NextAuth session cookie
  const browser = await chromium.launch();
  const context = await browser.newContext({ baseURL });
  const page = await context.newPage();

  await page.goto('/login');
  await page.fill('input[type="email"]', E2E_TEST_EMAIL);
  await page.fill('input[type="password"]', E2E_TEST_PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/dashboard/, { timeout: 15000 });

  // Step 3: Save authenticated state (cookies including next-auth.session-token)
  await context.storageState({ path: AUTH_STATE_PATH });
  console.log(`[global-setup] Auth state saved to ${AUTH_STATE_PATH}`);

  await browser.close();
}

export default globalSetup;
