import { Page, Browser, BrowserContext, expect } from '@playwright/test';

/**
 * Auth helper functions for E2E tests
 */

export interface TestUser {
  email: string;
  password: string;
  fullName?: string;
}

/** Pre-authenticated storage states produced by global-setup. */
export const USER_A_AUTH_PATH = 'tests/e2e/.auth/user.json';
export const USER_B_AUTH_PATH = 'tests/e2e/.auth/user-b.json';

const BASE_URL = process.env.BASE_URL || 'https://dev.podcaststudiohub.me';

/**
 * Generate a unique test user email
 */
export function generateTestUser(): TestUser {
  const timestamp = Date.now();
  return {
    email: `test-user-${timestamp}@example.com`,
    password: 'TestPassword123!',
    fullName: 'Test User',
  };
}

/**
 * Sign up a new user
 */
export async function signUp(page: Page, user: TestUser) {
  await page.goto('/signup');

  if (user.fullName) {
    await page.fill('input[id="fullName"]', user.fullName);
  }

  await page.fill('input[type="email"]', user.email);
  await page.fill('input[type="password"]', user.password);
  await page.click('button[type="submit"]');

  // After signup, redirect is /login (email verification required) or /dashboard (email disabled/auto-verified)
  await page.waitForURL(/\/(login|dashboard)/, { timeout: 10000 });
}

/**
 * Login with existing user credentials
 */
export async function login(page: Page, email: string, password: string) {
  await page.goto('/login');
  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', password);
  await page.click('button[type="submit"]');

  // Wait for redirect to dashboard
  await page.waitForURL(/\/dashboard/, { timeout: 15000 });
}

/**
 * Logout current user via the MainNav user-menu dropdown.
 */
export async function logout(page: Page) {
  await page.getByRole('button', { name: 'User menu' }).click();
  await page.getByRole('menuitem', { name: 'Logout' }).click();
  await page.waitForURL(/\/login/, { timeout: 10000 });
}

/**
 * Open a second, independently-authenticated browser context as User B.
 * User B is provisioned once by global-setup and persisted to USER_B_AUTH_PATH,
 * which keeps isolation tests within the dev registration rate limit (3/hr/IP).
 * Caller owns the returned context and must close() it (e.g. in a finally block).
 */
export async function createUserBContext(browser: Browser): Promise<BrowserContext> {
  return browser.newContext({ storageState: USER_B_AUTH_PATH, baseURL: BASE_URL });
}

/**
 * Sign up and login a new test user (one-step helper)
 */
export async function signUpAndLogin(page: Page): Promise<TestUser> {
  const user = generateTestUser();
  await signUp(page, user);
  await login(page, user.email, user.password);
  return user;
}

/**
 * Navigate to dashboard using pre-authenticated storageState.
 * Use this in non-auth tests instead of signUpAndLogin().
 */
export async function ensureLoggedIn(page: Page): Promise<TestUser> {
  await page.goto('/dashboard');
  if (page.url().includes('/login')) {
    throw new Error('ensureLoggedIn failed: storageState session is invalid or expired');
  }
  await page.waitForURL(/\/dashboard/, { timeout: 15000 });
  return {
    email: process.env.E2E_TEST_EMAIL || '',
    password: process.env.E2E_TEST_PASSWORD || '',
  };
}

/**
 * Check if user is authenticated (on dashboard)
 */
export async function isAuthenticated(page: Page): Promise<boolean> {
  try {
    return page.url().includes('/dashboard');
  } catch {
    return false;
  }
}
