# PodcastStudioHub E2E Test Suite

Automated end-to-end tests using Playwright.

## Test Coverage

### ✅ Implemented Tests
- `01-auth.spec.ts` - Authentication (signup, login, session management)

### 📝 Tests To Implement
- `02-projects.spec.ts` - Project management (CRUD operations)
- `03-episodes.spec.ts` - Episode management
- `04-content.spec.ts` - Content source management
- `05-generation.spec.ts` - Podcast generation workflow
- `06-navigation.spec.ts` - Navigation and UX flows
- `07-responsive.spec.ts` - Responsive design
- `08-performance.spec.ts` - Performance testing
- `09-accessibility.spec.ts` - Accessibility testing
- `10-integration.spec.ts` - Complete end-to-end workflows

## Running Tests

### Run all tests
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
- Pull requests to main
- Pushes to main
- Manual workflow dispatch

See `.github/workflows/playwright-tests.yml`

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
- `logout(page)` - Logout current user
- `signUpAndLogin(page)` - Combined signup and login

### Projects
- `createProject(page, data)` - Create new project
- `navigateToProject(page, id)` - Go to project page
- `verifyProjectExists(page, title)` - Check project in dashboard

### Episodes
- `createEpisode(page, projectId, data)` - Create new episode
- `addContentSource(page, episodeId, source)` - Add URL/text content
- `generatePodcast(page, episodeId)` - Start generation
- `waitForGeneration(page, episodeId)` - Wait for completion
- `verifyAudioPlayer(page)` - Check audio player exists

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
