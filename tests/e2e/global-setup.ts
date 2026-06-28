import { chromium, type Browser, type FullConfig } from '@playwright/test';
import { mkdirSync } from 'fs';
import { dirname } from 'path';

const USER_A_AUTH_PATH = 'tests/e2e/.auth/user.json';
const USER_B_AUTH_PATH = 'tests/e2e/.auth/user-b.json';

/**
 * Derive a deterministic, distinct second account from the primary E2E
 * credentials via plus-addressing. Persisting User B here (instead of signing up
 * a fresh user inside each isolation test) keeps the suite within the dev
 * registration rate limit (3/hr/IP) while still giving multi-tenant tests two
 * genuinely independent authenticated sessions.
 */
function deriveUserB(email: string): string {
  const at = email.lastIndexOf('@');
  if (at === -1) throw new Error(`E2E_TEST_EMAIL is not a valid email: ${email}`);
  return `${email.slice(0, at)}+isob${email.slice(at)}`;
}

/** Register (idempotent) then browser-login a user, saving its storageState. */
async function provisionUser(
  browser: Browser,
  baseURL: string,
  apiURL: string,
  email: string,
  password: string,
  fullName: string,
  statePath: string,
) {
  const registerResponse = await fetch(`${apiURL}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, full_name: fullName }),
  });

  if (registerResponse.ok) {
    console.log(`[global-setup] Registered ${email}`);
  } else if (registerResponse.status === 400 || registerResponse.status === 409) {
    console.log(`[global-setup] ${email} already exists`);
  } else {
    const body = await registerResponse.text();
    throw new Error(`[global-setup] Registration failed for ${email} (${registerResponse.status}): ${body}`);
  }

  const context = await browser.newContext({ baseURL });
  const page = await context.newPage();
  await page.goto('/login');
  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', password);
  await page.click('button[type="submit"]');

  try {
    await page.waitForURL(/\/dashboard/, { timeout: 15000 });
  } catch {
    const screenshot = `tests/e2e/.auth/login-failure-${statePath.replace(/[/.]/g, '_')}.png`;
    await page.screenshot({ path: screenshot });
    const currentURL = page.url();
    const pageText = (await page.textContent('body')) || '';
    await context.close();
    throw new Error(
      `[global-setup] Browser login failed for ${email} — stayed at: ${currentURL}\n` +
      `Page text: ${pageText.substring(0, 500)}\nScreenshot: ${screenshot}`
    );
  }

  await context.storageState({ path: statePath });
  await context.close();
  console.log(`[global-setup] Auth state saved to ${statePath}`);
}

async function globalSetup(config: FullConfig) {
  const E2E_TEST_EMAIL = process.env.E2E_TEST_EMAIL;
  const E2E_TEST_PASSWORD = process.env.E2E_TEST_PASSWORD;

  if (!E2E_TEST_EMAIL || !E2E_TEST_PASSWORD) {
    throw new Error(
      'E2E_TEST_EMAIL and E2E_TEST_PASSWORD must be set. ' +
      'In CI these come from GitHub Secrets. Locally, add them to a .env file or export them.'
    );
  }

  mkdirSync(dirname(USER_A_AUTH_PATH), { recursive: true });

  const baseURL = config.projects[0].use.baseURL || 'https://dev.podcaststudiohub.me';
  const apiURL = process.env.NEXT_PUBLIC_API_URL || `${baseURL}/api`;

  const browser = await chromium.launch();
  try {
    // User A — the shared session used by the bulk of the suite.
    await provisionUser(browser, baseURL, apiURL, E2E_TEST_EMAIL, E2E_TEST_PASSWORD, 'E2E Test User', USER_A_AUTH_PATH);
    // User B — a second independent tenant for multi-tenant isolation tests.
    await provisionUser(browser, baseURL, apiURL, deriveUserB(E2E_TEST_EMAIL), E2E_TEST_PASSWORD, 'E2E Test User B', USER_B_AUTH_PATH);
  } finally {
    await browser.close();
  }
}

export default globalSetup;
