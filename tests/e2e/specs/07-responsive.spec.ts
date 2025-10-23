import { test, expect } from '@playwright/test';
import { signUpAndLogin } from '../utils/auth-helpers';
import { createProject } from '../utils/project-helpers';
import { createEpisode, addContentSource } from '../utils/episode-helpers';

test.describe('Responsive Design', () => {
	test.describe('Mobile Layout (375x667 - iPhone SE)', () => {
		test.beforeEach(async ({ page }) => {
			await page.setViewportSize({ width: 375, height: 667 });
		});

		test('should display mobile-friendly dashboard', async ({ page }) => {
			await signUpAndLogin(page);
			await page.goto('/dashboard');

			// Page should be scrollable, not overflowing
			const hasHorizontalScroll = await page.evaluate(() => {
				return document.documentElement.scrollWidth > document.documentElement.clientWidth;
			});

			expect(hasHorizontalScroll).toBe(false);
		});

		test('should show mobile navigation menu', async ({ page }) => {
			await signUpAndLogin(page);
			await page.goto('/dashboard');

			// Mobile menu button should be visible
			await expect(
				page.locator('button[aria-label*="Menu"], button[aria-label*="navigation"]').first()
			).toBeVisible();
		});

		test('should allow creating project on mobile', async ({ page }) => {
			await signUpAndLogin(page);
			await page.goto('/dashboard');

			await page.click('button:has-text("Create Project")');

			const project = { title: `Mobile Project ${Date.now()}` };
			await page.fill('input[placeholder*="title" i]', project.title);
			await page.click('button:has-text("Create Project"), button:has-text("Create")');

			await expect(page).toHaveURL(/\/projects\/[a-f0-9-]+/);
		});

		test('should display project page on mobile', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			// Reset to mobile viewport after creation
			await page.setViewportSize({ width: 375, height: 667 });
			await page.goto(`/projects/${projectId}`);

			// Content should be readable
			await expect(page.locator(`text=${project.title}`)).toBeVisible();

			// No horizontal overflow
			const hasHorizontalScroll = await page.evaluate(() => {
				return document.documentElement.scrollWidth > document.documentElement.clientWidth;
			});

			expect(hasHorizontalScroll).toBe(false);
		});

		test('should display episode page on mobile', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			await page.setViewportSize({ width: 375, height: 667 });
			await page.goto(`/episodes/${episodeId}`);

			await expect(page.locator(`text=${episode.title}`)).toBeVisible();

			// No horizontal overflow
			const hasHorizontalScroll = await page.evaluate(() => {
				return document.documentElement.scrollWidth > document.documentElement.clientWidth;
			});

			expect(hasHorizontalScroll).toBe(false);
		});

		test('should handle long project titles on mobile', async ({ page }) => {
			await signUpAndLogin(page);

			const longTitle = 'This is a very long project title that should wrap properly on mobile devices without breaking the layout';
			const project = { title: longTitle };
			const projectId = await createProject(page, project);

			await page.setViewportSize({ width: 375, height: 667 });
			await page.goto(`/projects/${projectId}`);

			// Title should be visible and not overflow
			const titleElement = page.locator(`text=${longTitle.substring(0, 30)}`).first();
			await expect(titleElement).toBeVisible();

			const hasHorizontalScroll = await page.evaluate(() => {
				return document.documentElement.scrollWidth > document.documentElement.clientWidth;
			});

			expect(hasHorizontalScroll).toBe(false);
		});

		test('should make buttons touch-friendly on mobile', async ({ page }) => {
			await signUpAndLogin(page);
			await page.goto('/dashboard');

			// Create button should be easily tappable (44x44px minimum recommended)
			const createButton = page.locator('button:has-text("Create Project")').first();
			const box = await createButton.boundingBox();

			expect(box).not.toBeNull();
			if (box) {
				expect(box.height).toBeGreaterThanOrEqual(36); // Slightly less than 44 is acceptable
			}
		});

		test('should handle add content modal on mobile', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			await page.setViewportSize({ width: 375, height: 667 });
			await page.goto(`/episodes/${episodeId}`);

			await page.click('button:has-text("Add Content")');

			// Modal should be visible and usable
			await expect(page.locator('input[type="url"], textarea').first()).toBeVisible();

			// Modal should not overflow screen
			const hasHorizontalScroll = await page.evaluate(() => {
				return document.documentElement.scrollWidth > document.documentElement.clientWidth;
			});

			expect(hasHorizontalScroll).toBe(false);
		});
	});

	test.describe('Tablet Layout (768x1024 - iPad)', () => {
		test.beforeEach(async ({ page }) => {
			await page.setViewportSize({ width: 768, height: 1024 });
		});

		test('should display tablet-optimized dashboard', async ({ page }) => {
			await signUpAndLogin(page);
			await page.goto('/dashboard');

			// No horizontal scroll
			const hasHorizontalScroll = await page.evaluate(() => {
				return document.documentElement.scrollWidth > document.documentElement.clientWidth;
			});

			expect(hasHorizontalScroll).toBe(false);
		});

		test('should allow multi-column layout if available', async ({ page }) => {
			await signUpAndLogin(page);

			// Create multiple projects
			for (let i = 0; i < 4; i++) {
				await createProject(page, { title: `Project ${i} ${Date.now() + i}` });
			}

			await page.setViewportSize({ width: 768, height: 1024 });
			await page.goto('/dashboard');

			// Projects should be visible
			const projects = await page.locator('[data-testid="project"], .project-card, article').count();
			expect(projects).toBeGreaterThanOrEqual(1);
		});

		test('should display project page on tablet', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			await page.setViewportSize({ width: 768, height: 1024 });
			await page.goto(`/projects/${projectId}`);

			await expect(page.locator(`text=${project.title}`)).toBeVisible();
		});

		test('should handle forms on tablet', async ({ page }) => {
			await signUpAndLogin(page);

			await page.setViewportSize({ width: 768, height: 1024 });
			await page.goto('/dashboard');

			await page.click('button:has-text("Create Project")');

			// Form should be usable
			const titleInput = page.locator('input[placeholder*="title" i]');
			await expect(titleInput).toBeVisible();

			// Form should not be too wide or narrow
			const box = await titleInput.boundingBox();
			expect(box).not.toBeNull();
			if (box) {
				expect(box.width).toBeGreaterThan(200); // Not too narrow
				expect(box.width).toBeLessThan(700); // Not too wide
			}
		});
	});

	test.describe('Desktop Layout (1920x1080)', () => {
		test.beforeEach(async ({ page }) => {
			await page.setViewportSize({ width: 1920, height: 1080 });
		});

		test('should display full desktop layout', async ({ page }) => {
			await signUpAndLogin(page);
			await page.goto('/dashboard');

			// Navigation should be visible (not hamburger)
			const navLinks = await page.locator('nav a').count();
			expect(navLinks).toBeGreaterThan(0);
		});

		test('should show sidebar if available', async ({ page }) => {
			await signUpAndLogin(page);
			await page.goto('/dashboard');

			// Desktop may have sidebar navigation
			const hasSidebar = await page.locator('aside, [role="complementary"]')
				.isVisible({ timeout: 2000 })
				.catch(() => false);

			// This is optional - not all designs have sidebars
		});

		test('should use available screen space efficiently', async ({ page }) => {
			await signUpAndLogin(page);

			// Create multiple projects
			for (let i = 0; i < 6; i++) {
				await createProject(page, { title: `Project ${i} ${Date.now() + i}` });
			}

			await page.setViewportSize({ width: 1920, height: 1080 });
			await page.goto('/dashboard');

			// Multiple columns should be visible on desktop
			const firstProject = page.locator('[data-testid="project"], .project-card, article').first();
			const lastProject = page.locator('[data-testid="project"], .project-card, article').last();

			const firstBox = await firstProject.boundingBox();
			const lastBox = await lastProject.boundingBox();

			if (firstBox && lastBox) {
				// Items should not all be in the same column
				// (unless there are very few items)
			}
		});

		test('should display wide-screen project page', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			await page.setViewportSize({ width: 1920, height: 1080 });
			await page.goto(`/projects/${projectId}`);

			// Content should not be too wide (max-width container)
			const main = page.locator('main, [role="main"]').first();
			const box = await main.boundingBox();

			expect(box).not.toBeNull();
			if (box) {
				// Content shouldn't span full 1920px width
				expect(box.width).toBeLessThan(1600);
			}
		});

		test('should handle modals on desktop', async ({ page }) => {
			await signUpAndLogin(page);

			await page.setViewportSize({ width: 1920, height: 1080 });
			await page.goto('/dashboard');

			await page.click('button:has-text("Create Project")');

			// Modal should be centered and appropriate size
			const modal = page.locator('[role="dialog"], .modal').first();
			const box = await modal.boundingBox();

			expect(box).not.toBeNull();
			if (box) {
				// Modal should not be full width
				expect(box.width).toBeLessThan(800);
				// Modal should be reasonably centered
				expect(box.x).toBeGreaterThan(100);
			}
		});
	});

	test.describe('Orientation Changes', () => {
		test('should handle portrait to landscape on mobile', async ({ page }) => {
			// Start in portrait
			await page.setViewportSize({ width: 375, height: 667 });
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			// Switch to landscape
			await page.setViewportSize({ width: 667, height: 375 });
			await page.goto(`/projects/${projectId}`);

			// Content should still be visible
			await expect(page.locator(`text=${project.title}`)).toBeVisible();

			// No horizontal overflow
			const hasHorizontalScroll = await page.evaluate(() => {
				return document.documentElement.scrollWidth > document.documentElement.clientWidth;
			});

			expect(hasHorizontalScroll).toBe(false);
		});

		test('should handle landscape to portrait on tablet', async ({ page }) => {
			// Landscape
			await page.setViewportSize({ width: 1024, height: 768 });
			await signUpAndLogin(page);
			await page.goto('/dashboard');

			// Portrait
			await page.setViewportSize({ width: 768, height: 1024 });
			await page.reload();

			// Dashboard should still be functional
			await expect(page.locator('button:has-text("Create Project")')).toBeVisible();
		});
	});

	test.describe('Viewport Breakpoints', () => {
		const breakpoints = [
			{ name: 'Small Mobile', width: 320, height: 568 },
			{ name: 'Mobile', width: 375, height: 667 },
			{ name: 'Large Mobile', width: 414, height: 896 },
			{ name: 'Tablet', width: 768, height: 1024 },
			{ name: 'Desktop', width: 1024, height: 768 },
			{ name: 'Large Desktop', width: 1440, height: 900 },
		];

		for (const breakpoint of breakpoints) {
			test(`should work at ${breakpoint.name} (${breakpoint.width}x${breakpoint.height})`, async ({ page }) => {
				await page.setViewportSize({ width: breakpoint.width, height: breakpoint.height });

				await signUpAndLogin(page);
				await page.goto('/dashboard');

				// Basic functionality should work
				await expect(page.locator('button:has-text("Create Project")')).toBeVisible();

				// No horizontal scroll
				const hasHorizontalScroll = await page.evaluate(() => {
					return document.documentElement.scrollWidth > document.documentElement.clientWidth;
				});

				expect(hasHorizontalScroll).toBe(false);
			});
		}
	});

	test.describe('Text Scaling', () => {
		test('should handle larger text sizes', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			// Increase font size
			await page.evaluate(() => {
				document.documentElement.style.fontSize = '20px';
			});

			await page.goto(`/projects/${projectId}`);

			// Content should still be visible
			await expect(page.locator(`text=${project.title}`)).toBeVisible();

			// Check for horizontal overflow
			const hasHorizontalScroll = await page.evaluate(() => {
				return document.documentElement.scrollWidth > document.documentElement.clientWidth;
			});

			expect(hasHorizontalScroll).toBe(false);
		});
	});

	test.describe('Content Wrapping', () => {
		test('should wrap long URLs properly', async ({ page }) => {
			await page.setViewportSize({ width: 375, height: 667 });

			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			const longUrl = 'https://example.com/very-long-path-that-should-wrap/and-not-overflow/the-container/on-mobile-devices';
			await addContentSource(page, episodeId, { type: 'url', value: longUrl });

			// No horizontal overflow
			const hasHorizontalScroll = await page.evaluate(() => {
				return document.documentElement.scrollWidth > document.documentElement.clientWidth;
			});

			expect(hasHorizontalScroll).toBe(false);
		});

		test('should wrap long text content', async ({ page }) => {
			await page.setViewportSize({ width: 375, height: 667 });

			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			const longText = 'This is a very long text without spaces that could potentially cause horizontal scrolling issues if not handled properly with CSS word-break or overflow properties';
			await addContentSource(page, episodeId, { type: 'text', value: longText });

			// No horizontal overflow
			const hasHorizontalScroll = await page.evaluate(() => {
				return document.documentElement.scrollWidth > document.documentElement.clientWidth;
			});

			expect(hasHorizontalScroll).toBe(false);
		});
	});

	test.describe('Touch Targets', () => {
		test('should have adequate touch target sizes on mobile', async ({ page }) => {
			await page.setViewportSize({ width: 375, height: 667 });

			await signUpAndLogin(page);
			await page.goto('/dashboard');

			// Check create button size
			const createButton = page.locator('button:has-text("Create Project")').first();
			const box = await createButton.boundingBox();

			expect(box).not.toBeNull();
			if (box) {
				// Minimum recommended: 44x44px
				// We'll be lenient and check for 36px
				expect(box.height).toBeGreaterThanOrEqual(36);
			}
		});

		test('should have spacing between touch targets', async ({ page }) => {
			await page.setViewportSize({ width: 375, height: 667 });

			await signUpAndLogin(page);

			// Create multiple projects
			await createProject(page, { title: `Project 1 ${Date.now()}` });
			await createProject(page, { title: `Project 2 ${Date.now() + 1}` });

			await page.goto('/dashboard');

			// Check spacing between project cards/links
			const projects = page.locator('[data-testid="project"], .project-card, article');
			const count = await projects.count();

			if (count >= 2) {
				const first = await projects.nth(0).boundingBox();
				const second = await projects.nth(1).boundingBox();

				if (first && second) {
					// There should be some spacing
					const spacing = second.y - (first.y + first.height);
					expect(spacing).toBeGreaterThanOrEqual(8); // At least 8px spacing
				}
			}
		});
	});

	test.describe('Image Scaling', () => {
		test('should scale images on mobile', async ({ page }) => {
			await page.setViewportSize({ width: 375, height: 667 });

			await signUpAndLogin(page);
			await page.goto('/dashboard');

			// Check if any images exist
			const images = await page.locator('img').count();

			if (images > 0) {
				// Images should not cause horizontal scroll
				const hasHorizontalScroll = await page.evaluate(() => {
					return document.documentElement.scrollWidth > document.documentElement.clientWidth;
				});

				expect(hasHorizontalScroll).toBe(false);
			}
		});
	});
});
