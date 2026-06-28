import { test, expect } from '@playwright/test';
import { generateTestUser, signUp, login, logout } from '../utils/auth-helpers';

// Auth tests must start unauthenticated — override the shared storageState
test.use({ storageState: { cookies: [], origins: [] } });

// Pre-seeded E2E credentials — avoids creating new users in login/session tests,
// which keeps registration API calls within the rate limit (3/hour per IP in dev).
const E2E_EMAIL = process.env.E2E_TEST_EMAIL ?? 'e2e-test@example.com';
const E2E_PASSWORD = process.env.E2E_TEST_PASSWORD ?? 'E2eTestPassword123!';

test.describe('Authentication', () => {
  test.describe('Sign Up', () => {
    test('should display signup form', async ({ page }) => {
      await page.goto('/signup');

      // Verify form elements
      await expect(page.locator('input[type="email"]')).toBeVisible();
      await expect(page.locator('input[type="password"]')).toBeVisible();
      await expect(page.locator('button[type="submit"]')).toBeVisible();
    });

    test('should validate required fields', async ({ page }) => {
      await page.goto('/signup');

      // Try submitting empty form
      await page.click('button[type="submit"]');

      // Should show validation (browser native or custom)
      const emailInput = page.locator('input[type="email"]');
      await expect(emailInput).toHaveAttribute('required', '');
    });

    test('should create new user account', async ({ page }) => {
      const user = generateTestUser();
      await signUp(page, user);

      // Should redirect to login
      await expect(page).toHaveURL(/\/login/);
    });

    test('should show error for existing email', async ({ page }) => {
      // Use the pre-seeded E2E user — avoids a second registration API call
      await page.goto('/signup');
      await page.fill('input[type="email"]', E2E_EMAIL);
      await page.fill('input[type="password"]', E2E_PASSWORD);
      await page.click('button[type="submit"]');

      // Should show error
      await expect(page.locator('text=/error|already|exist/i')).toBeVisible({ timeout: 5000 });
    });

    test('should enforce password minimum length', async ({ page }) => {
      await page.goto('/signup');

      await page.fill('input[type="email"]', 'test@example.com');
      await page.fill('input[type="password"]', 'short'); // Less than 8 chars
      await page.click('button[type="submit"]');

      // Should show validation error
      const passwordInput = page.locator('input[type="password"]');
      await expect(passwordInput).toHaveAttribute('minlength', '8');
    });
  });

  test.describe('Login', () => {
    // Uses pre-seeded E2E credentials — no registration calls needed here.
    // Creating a fresh user per test would exhaust the registration rate limit (3/hour per IP).

    test('should display login form', async ({ page }) => {
      await page.goto('/login');

      await expect(page.locator('input[type="email"]')).toBeVisible();
      await expect(page.locator('input[type="password"]')).toBeVisible();
      await expect(page.locator('button[type="submit"]')).toBeVisible();
    });

    test('should login with valid credentials', async ({ page }) => {
      await login(page, E2E_EMAIL, E2E_PASSWORD);

      // Should redirect to dashboard
      await expect(page).toHaveURL(/\/dashboard/);
    });

    test('should show error for invalid credentials', async ({ page }) => {
      await page.goto('/login');

      await page.fill('input[type="email"]', E2E_EMAIL);
      await page.fill('input[type="password"]', 'WrongPassword123');
      await page.click('button[type="submit"]');

      // Should show error message
      await expect(page.locator('text=/error|invalid|incorrect/i')).toBeVisible({ timeout: 5000 });
    });

    test('should show error for non-existent user', async ({ page }) => {
      await page.goto('/login');

      await page.fill('input[type="email"]', 'nonexistent@example.com');
      await page.fill('input[type="password"]', 'SomePassword123');
      await page.click('button[type="submit"]');

      // Should show error
      await expect(page.locator('text=/error|not found|invalid/i')).toBeVisible({ timeout: 5000 });
    });
  });

  test.describe('Session Management', () => {
    // Uses pre-seeded E2E credentials — no registration needed.
    test.beforeEach(async ({ page }) => {
      await login(page, E2E_EMAIL, E2E_PASSWORD);
    });

    test('should persist session on page reload', async ({ page }) => {
      await page.goto('/dashboard');
      await expect(page).toHaveURL(/\/dashboard/);

      // Reload page
      await page.reload();

      // Should still be on dashboard (logged in)
      await expect(page).toHaveURL(/\/dashboard/);
    });

    test('should protect dashboard route when not logged in', async ({ page }) => {
      await logout(page);
      await page.goto('/dashboard');
      await expect(page).toHaveURL(/\/login/);
    });

    test('should protect project routes when not logged in', async ({ page }) => {
      await logout(page);
      await page.goto('/projects/test-id');
      await expect(page).toHaveURL(/\/login/);
    });

    test('should protect episode routes when not logged in', async ({ page }) => {
      await logout(page);
      await page.goto('/episodes/test-id');
      await expect(page).toHaveURL(/\/login/);
    });
  });

  test.describe('Navigation Links', () => {
    test('should navigate from login to signup', async ({ page }) => {
      await page.goto('/login');

      // Click signup link
      await page.click('a:has-text("Sign up"), a:has-text("Sign Up")');

      await expect(page).toHaveURL(/\/signup/);
    });

    test('should navigate from signup to login', async ({ page }) => {
      await page.goto('/signup');

      // Click login link
      await page.click('a:has-text("Sign in"), a:has-text("Login"), a:has-text("Log in")');

      await expect(page).toHaveURL(/\/login/);
    });
  });
});
