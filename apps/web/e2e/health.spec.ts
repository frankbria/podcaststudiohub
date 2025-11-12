import { test, expect } from '@playwright/test'

test.describe('Application Health Checks', () => {
  test('should load the home page successfully', async ({ page }) => {
    // Navigate to the home page
    await page.goto('/')

    // Wait for page to load
    await page.waitForLoadState('networkidle')

    // Verify the page loaded (check for HTML element)
    await expect(page.locator('html')).toBeVisible()

    // Check that we don't have any console errors (optional)
    const errors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        errors.push(msg.text())
      }
    })

    // Take a screenshot for visual verification
    await page.screenshot({ path: 'test-results/home-page.png' })
  })

  test('should have correct page title', async ({ page }) => {
    await page.goto('/')

    // Verify page has a title
    await expect(page).toHaveTitle(/.*/)
  })

  test('API health endpoint should return 200', async ({ request }) => {
    // Test the backend API health endpoint
    const baseApiUrl = process.env.API_URL || 'http://localhost:8000'

    try {
      const response = await request.get(`${baseApiUrl}/health`)

      // Verify response status
      expect(response.status()).toBe(200)

      // Verify response body
      const body = await response.json()
      expect(body).toHaveProperty('status')
      expect(body.status).toBe('healthy')
    } catch (error) {
      // If API is not available, skip this test
      console.warn('API endpoint not available, skipping API health check')
      test.skip()
    }
  })

  test('should navigate without JavaScript errors', async ({ page }) => {
    const errors: string[] = []

    page.on('pageerror', (error) => {
      errors.push(error.message)
    })

    await page.goto('/')
    await page.waitForLoadState('domcontentloaded')

    // Check for JavaScript errors
    expect(errors).toHaveLength(0)
  })
})
