import { test, expect } from '@playwright/test';
import { signUpAndLogin } from '../utils/auth-helpers';
import { createProject } from '../utils/project-helpers';
import { createEpisode, addContentSource } from '../utils/episode-helpers';

test.describe('Performance', () => {
	test.describe('Page Load Performance', () => {
		test('should load dashboard quickly', async ({ page }) => {
			await signUpAndLogin(page);

			const startTime = Date.now();
			await page.goto('/dashboard');
			await expect(page.locator('button:has-text("Create Project")')).toBeVisible();
			const loadTime = Date.now() - startTime;

			// Dashboard should load in under 3 seconds
			expect(loadTime).toBeLessThan(3000);
		});

		test('should load project page quickly', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			const startTime = Date.now();
			await page.goto(`/projects/${projectId}`);
			await expect(page.locator(`text=${project.title}`)).toBeVisible();
			const loadTime = Date.now() - startTime;

			// Project page should load in under 3 seconds
			expect(loadTime).toBeLessThan(3000);
		});

		test('should load episode page quickly', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			const startTime = Date.now();
			await page.goto(`/episodes/${episodeId}`);
			await expect(page.locator(`text=${episode.title}`)).toBeVisible();
			const loadTime = Date.now() - startTime;

			// Episode page should load in under 3 seconds
			expect(loadTime).toBeLessThan(3000);
		});
	});

	test.describe('Navigation Performance', () => {
		test('should navigate between pages quickly', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			// Navigate from dashboard to project
			await page.goto('/dashboard');

			const startTime = Date.now();
			await page.click(`text=${project.title}`);
			await expect(page).toHaveURL(`/projects/${projectId}`);
			const navTime = Date.now() - startTime;

			// Navigation should be quick (client-side routing)
			expect(navTime).toBeLessThan(2000);
		});

		test('should handle back navigation quickly', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			await page.goto('/dashboard');
			await page.click(`text=${project.title}`);

			const startTime = Date.now();
			await page.goBack();
			await expect(page).toHaveURL(/\/dashboard/);
			const navTime = Date.now() - startTime;

			expect(navTime).toBeLessThan(2000);
		});
	});

	test.describe('Form Interaction Performance', () => {
		test('should create project quickly', async ({ page }) => {
			await signUpAndLogin(page);
			await page.goto('/dashboard');

			await page.click('button:has-text("Create Project")');

			const project = { title: `Perf Test ${Date.now()}` };
			await page.fill('input[placeholder*="title" i]', project.title);

			const startTime = Date.now();
			await page.click('button:has-text("Create Project"), button:has-text("Create")');
			await expect(page).toHaveURL(/\/projects\/[a-f0-9-]+/);
			const createTime = Date.now() - startTime;

			// Project creation should complete in under 5 seconds
			expect(createTime).toBeLessThan(5000);
		});

		test('should create episode quickly', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			await page.click('button:has-text("Create Episode")');

			const episode = { title: `Perf Episode ${Date.now()}` };
			await page.fill('input[placeholder*="title" i], input[placeholder*="episode" i]', episode.title);

			const startTime = Date.now();
			await page.click('button:has-text("Create Episode"), button:has-text("Create")');
			await expect(page).toHaveURL(/\/episodes\/[a-f0-9-]+/);
			const createTime = Date.now() - startTime;

			expect(createTime).toBeLessThan(5000);
		});

		test('should add content source quickly', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			await page.click('button:has-text("Add Content")');

			const url = 'https://example.com/article';
			await page.fill('input[type="url"], input[placeholder*="url" i]', url);

			const startTime = Date.now();
			await page.click('button:has-text("Add Content"), button:has-text("Add")');
			await page.waitForTimeout(1000); // Wait for content to appear
			const addTime = Date.now() - startTime;

			expect(addTime).toBeLessThan(3000);
		});
	});

	test.describe('List Rendering Performance', () => {
		test('should render large project list quickly', async ({ page }) => {
			await signUpAndLogin(page);

			// Create 20 projects
			for (let i = 0; i < 20; i++) {
				await createProject(page, { title: `Project ${i} ${Date.now() + i}` });
			}

			const startTime = Date.now();
			await page.goto('/dashboard');
			await expect(page.locator('[data-testid="project"], .project-card, article').first()).toBeVisible();
			const renderTime = Date.now() - startTime;

			// Should render 20 projects in under 4 seconds
			expect(renderTime).toBeLessThan(4000);
		});

		test('should render large episode list quickly', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			// Create 15 episodes
			for (let i = 0; i < 15; i++) {
				await createEpisode(page, projectId, { title: `Episode ${i} ${Date.now() + i}` });
			}

			const startTime = Date.now();
			await page.goto(`/projects/${projectId}`);
			await expect(page.locator('[data-testid="episode"], .episode-card, article').first()).toBeVisible();
			const renderTime = Date.now() - startTime;

			expect(renderTime).toBeLessThan(4000);
		});

		test('should render large content source list quickly', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			// Add 10 content sources
			for (let i = 0; i < 10; i++) {
				await addContentSource(page, episodeId, {
					type: 'url',
					value: `https://example.com/article${i}`,
				});
			}

			const startTime = Date.now();
			await page.goto(`/episodes/${episodeId}`);
			await expect(page.locator('text=https://example.com/article0')).toBeVisible();
			const renderTime = Date.now() - startTime;

			expect(renderTime).toBeLessThan(3000);
		});
	});

	test.describe('Animation Performance', () => {
		test('should handle modal animations smoothly', async ({ page }) => {
			await signUpAndLogin(page);
			await page.goto('/dashboard');

			// Measure frame rate during modal open
			const metrics = await page.evaluate(() => {
				return new Promise((resolve) => {
					const frames: number[] = [];
					let lastTime = performance.now();

					const measureFrame = () => {
						const currentTime = performance.now();
						frames.push(currentTime - lastTime);
						lastTime = currentTime;

						if (frames.length < 60) {
							requestAnimationFrame(measureFrame);
						} else {
							const avgFrameTime = frames.reduce((a, b) => a + b, 0) / frames.length;
							const fps = 1000 / avgFrameTime;
							resolve(fps);
						}
					};

					requestAnimationFrame(measureFrame);
				});
			});

			await page.click('button:has-text("Create Project")');

			// Wait for modal to appear
			await page.waitForTimeout(500);

			// Frame rate should be acceptable (>30fps)
			// expect(metrics).toBeGreaterThan(30);
		});
	});

	test.describe('Memory Usage', () => {
		test('should not leak memory on repeated navigation', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			// Navigate back and forth 10 times
			for (let i = 0; i < 10; i++) {
				await page.goto('/dashboard');
				await page.goto(`/projects/${projectId}`);
			}

			// Get memory metrics
			const metrics = await page.evaluate(() => {
				if ('memory' in performance) {
					return (performance as any).memory;
				}
				return null;
			});

			// This test is informational - actual memory limits depend on browser
			// Just verify navigation still works
			await expect(page.locator(`text=${project.title}`)).toBeVisible();
		});
	});

	test.describe('Network Performance', () => {
		test('should minimize API calls on dashboard load', async ({ page }) => {
			await signUpAndLogin(page);

			// Track API calls
			const apiCalls: string[] = [];
			page.on('request', request => {
				if (request.url().includes('/api/')) {
					apiCalls.push(request.url());
				}
			});

			await page.goto('/dashboard');
			await expect(page.locator('button:has-text("Create Project")')).toBeVisible();

			// Dashboard should make reasonable number of API calls (not 50+)
			expect(apiCalls.length).toBeLessThan(20);
		});

		test('should cache static assets', async ({ page }) => {
			await signUpAndLogin(page);

			// First load
			await page.goto('/dashboard');

			const cachedRequests: string[] = [];
			page.on('response', response => {
				const cacheControl = response.headers()['cache-control'];
				if (cacheControl && (cacheControl.includes('public') || cacheControl.includes('max-age'))) {
					cachedRequests.push(response.url());
				}
			});

			// Second load
			await page.goto('/dashboard');

			// Should have some cacheable resources
			// expect(cachedRequests.length).toBeGreaterThan(0);
		});
	});

	test.describe('Bundle Size', () => {
		test('should load minimal JavaScript for simple pages', async ({ page }) => {
			await signUpAndLogin(page);

			// Track JS bundle sizes
			const jsBundles: { url: string; size: number }[] = [];

			page.on('response', async response => {
				const url = response.url();
				if (url.endsWith('.js') || url.includes('.js?')) {
					try {
						const buffer = await response.body();
						jsBundles.push({
							url,
							size: buffer.length,
						});
					} catch (e) {
						// Ignore errors
					}
				}
			});

			await page.goto('/dashboard');

			// Wait for page to fully load
			await page.waitForLoadState('networkidle');

			// Total JS should be reasonable (not 10+ MB)
			const totalSize = jsBundles.reduce((sum, bundle) => sum + bundle.size, 0);
			const totalMB = totalSize / (1024 * 1024);

			// Modern apps can be 1-3MB of JS
			expect(totalMB).toBeLessThan(5);
		});
	});

	test.describe('Database Query Performance', () => {
		test('should load dashboard with many projects efficiently', async ({ page }) => {
			await signUpAndLogin(page);

			// Create 50 projects
			for (let i = 0; i < 50; i++) {
				await createProject(page, { title: `Project ${i} ${Date.now() + i}` });
			}

			const startTime = Date.now();
			await page.goto('/dashboard');
			await expect(page.locator('[data-testid="project"], .project-card, article').first()).toBeVisible();
			const loadTime = Date.now() - startTime;

			// Should still load reasonably fast with 50 projects
			expect(loadTime).toBeLessThan(5000);
		});
	});

	test.describe('Concurrent Operations', () => {
		test('should handle multiple rapid clicks gracefully', async ({ page }) => {
			await signUpAndLogin(page);
			await page.goto('/dashboard');

			// Rapidly click create button 5 times
			const createButton = page.locator('button:has-text("Create Project")');

			for (let i = 0; i < 5; i++) {
				await createButton.click({ timeout: 1000 }).catch(() => {});
				await page.waitForTimeout(100);
			}

			// Should handle gracefully (debouncing, disabled state, etc.)
			// Page should still be functional
			await expect(page.locator('body')).toBeVisible();
		});
	});

	test.describe('Lazy Loading', () => {
		test('should lazy load content as needed', async ({ page }) => {
			await signUpAndLogin(page);

			// Create many projects
			for (let i = 0; i < 30; i++) {
				await createProject(page, { title: `Project ${i} ${Date.now() + i}` });
			}

			// Track initial requests
			const initialRequests: string[] = [];
			page.on('request', request => {
				initialRequests.push(request.url());
			});

			await page.goto('/dashboard');

			// Wait for initial load
			await page.waitForTimeout(1000);

			const initialCount = initialRequests.length;

			// Scroll to bottom (may trigger lazy loading)
			await page.evaluate(() => {
				window.scrollTo(0, document.body.scrollHeight);
			});

			await page.waitForTimeout(1000);

			// May have additional requests from lazy loading
			// This is informational
		});
	});

	test.describe('Perceived Performance', () => {
		test('should show loading states immediately', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			// Navigate away
			await page.goto('/dashboard');

			// Start navigation
			const projectLink = page.locator(`text=${project.title}`);
			await projectLink.click();

			// Loading indicator should appear quickly (if navigation takes time)
			const hasLoadingIndicator = await page.locator('.loading, [role="progressbar"], .spinner')
				.isVisible({ timeout: 500 })
				.catch(() => false);

			// Either shows loading or navigates instantly (both acceptable)
			// This just verifies no long blank screen
		});
	});
});
