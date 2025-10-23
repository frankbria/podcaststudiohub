import { Page, expect } from '@playwright/test';

/**
 * Auth helper functions for E2E tests
 */

export interface TestUser {
  email: string;
  password: string;
  fullName?: string;
}

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

  // Should redirect to login page
  await expect(page).toHaveURL(/\/login/);
}

/**
 * Login with existing user credentials
 */
export async function login(page: Page, email: string, password: string) {
  await page.goto('/login');
  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', password);
  await page.click('button[type="submit"]');

  // Should redirect to dashboard
  await expect(page).toHaveURL(/\/dashboard/);
}

/**
 * Logout current user
 */
export async function logout(page: Page) {
  // Look for logout button (adjust selector based on your UI)
  const logoutButton = page.locator('button:has-text("Logout"), button:has-text("Log out"), a:has-text("Logout")').first();

  if (await logoutButton.isVisible({ timeout: 1000 }).catch(() => false)) {
    await logoutButton.click();
  }
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
 * Check if user is authenticated (on dashboard)
 */
export async function isAuthenticated(page: Page): Promise<boolean> {
  try {
    return page.url().includes('/dashboard');
  } catch {
    return false;
  }
}
