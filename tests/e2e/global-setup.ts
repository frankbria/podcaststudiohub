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
    throw new Error(`[global-setup] Registration failed (${registerResponse.status}): ${body}`);
  }

  // Step 2: Verify credentials work via direct API login (fast fail)
  const loginResponse = await fetch(`${apiURL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email: E2E_TEST_EMAIL,
      password: E2E_TEST_PASSWORD,
    }),
  });

  if (!loginResponse.ok) {
    const body = await loginResponse.text();
    throw new Error(
      `[global-setup] API login failed (${loginResponse.status}): ${body}\n` +
      'The user may have been registered with different credentials. ' +
      'Delete the user from the dev database or update the GitHub Secret password to match.'
    );
  }
  console.log('[global-setup] API login verified');

  // Step 3: Log in via the browser to get the NextAuth session cookie
  const browser = await chromium.launch();
  const context = await browser.newContext({ baseURL });
  const page = await context.newPage();

  await page.goto('/login');
  await page.fill('input[type="email"]', E2E_TEST_EMAIL);
  await page.fill('input[type="password"]', E2E_TEST_PASSWORD);
  await page.click('button[type="submit"]');

  try {
    await page.waitForURL(/\/dashboard/, { timeout: 15000 });
  } catch {
    const screenshot = 'tests/e2e/.auth/login-failure.png';
    await page.screenshot({ path: screenshot });
    const currentURL = page.url();
    const pageContent = await page.textContent('body') || '';
    await browser.close();
    throw new Error(
      `[global-setup] Browser login failed — page stayed at: ${currentURL}\n` +
      `Page text: ${pageContent.substring(0, 500)}\n` +
      `Screenshot saved to: ${screenshot}`
    );
  }

  // Step 4: Save authenticated state (cookies including next-auth.session-token)
  await context.storageState({ path: AUTH_STATE_PATH });
  console.log(`[global-setup] Auth state saved to ${AUTH_STATE_PATH}`);

  await browser.close();
}

export default globalSetup;
