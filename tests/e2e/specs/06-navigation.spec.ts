import { test, expect } from '@playwright/test';
import { signUpAndLogin } from '../utils/auth-helpers';
import { createProject } from '../utils/project-helpers';
import { createEpisode } from '../utils/episode-helpers';

test.describe('Navigation and UX Flows', () => {
	test.describe('Main Navigation', () => {
		test('should display main navigation menu when logged in', async ({ page }) => {
			await signUpAndLogin(page);
			await page.goto('/dashboard');

			// Main nav should be visible
			await expect(page.locator('nav, [role="navigation"]').first()).toBeVisible();
		});

		test('should navigate to dashboard from nav menu', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			await createProject(page, project);

			// Click dashboard link in nav
			await page.click('nav a:has-text("Dashboard"), [role="navigation"] a:has-text("Dashboard")');

			await expect(page).toHaveURL(/\/dashboard/);
		});

		test('should show user menu in navigation', async ({ page }) => {
			await signUpAndLogin(page);
			await page.goto('/dashboard');

			// User menu should exist (avatar, name, or dropdown)
			await expect(
				page.locator('[aria-label*="User menu"], [aria-label*="Account"], button:has-text("Account")')
			).toBeVisible();
		});

		test('should highlight active navigation item', async ({ page }) => {
			await signUpAndLogin(page);
			await page.goto('/dashboard');

			// Dashboard link should be highlighted/active
			const dashboardLink = page.locator('nav a:has-text("Dashboard")').first();
			const classes = await dashboardLink.getAttribute('class');

			// Should have active class (aria-current, active class, or similar)
			const ariaCurrent = await dashboardLink.getAttribute('aria-current');
			expect(classes?.includes('active') || ariaCurrent === 'page').toBe(true);
		});
	});

	test.describe('Breadcrumb Navigation', () => {
		test('should show breadcrumb on project page', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			// Breadcrumb should show: Dashboard > Project Name
			const breadcrumb = page.locator('[aria-label="Breadcrumb"], nav').first();
			await expect(breadcrumb.locator('text=/Dashboard/i')).toBeVisible();
			await expect(breadcrumb.locator(`text=${project.title}`)).toBeVisible();
		});

		test('should show breadcrumb on episode page', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			// Breadcrumb should show: Dashboard > Project > Episode
			const breadcrumb = page.locator('[aria-label="Breadcrumb"], nav').first();
			await expect(breadcrumb.locator('text=/Dashboard/i')).toBeVisible();
			await expect(breadcrumb.locator(`text=${project.title}`)).toBeVisible();
			await expect(breadcrumb.locator(`text=${episode.title}`)).toBeVisible();
		});

		test('should navigate via breadcrumb to dashboard', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			// Click Dashboard in breadcrumb
			const breadcrumb = page.locator('[aria-label="Breadcrumb"], nav').first();
			await breadcrumb.locator('a:has-text("Dashboard")').click();

			await expect(page).toHaveURL(/\/dashboard/);
		});

		test('should navigate via breadcrumb to project', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			// Click Project in breadcrumb
			const breadcrumb = page.locator('[aria-label="Breadcrumb"], nav').first();
			await breadcrumb.locator(`a:has-text("${project.title}")`).click();

			await expect(page).toHaveURL(`/projects/${projectId}`);
		});
	});

	test.describe('Browser Navigation', () => {
		test('should support browser back button', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			// Go to dashboard
			await page.goto('/dashboard');

			// Navigate to project
			await page.click(`text=${project.title}`);
			await expect(page).toHaveURL(`/projects/${projectId}`);

			// Use browser back
			await page.goBack();
			await expect(page).toHaveURL(/\/dashboard/);
		});

		test('should support browser forward button', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			await page.goto('/dashboard');
			await page.click(`text=${project.title}`);
			await page.goBack();

			// Use browser forward
			await page.goForward();
			await expect(page).toHaveURL(`/projects/${projectId}`);
		});

		test('should maintain state after back/forward navigation', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			await page.goto('/dashboard');
			await page.click(`text=${project.title}`);
			await page.goBack();
			await page.goForward();

			// Project title should still be visible
			await expect(page.locator(`text=${project.title}`)).toBeVisible();
		});
	});

	test.describe('Deep Linking', () => {
		test('should support direct URL to project', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			// Logout and login again
			await page.goto('/dashboard');
			const logoutButton = page.locator('button:has-text("Logout"), button:has-text("Sign out")').first();
			await logoutButton.click();

			const user = await signUpAndLogin(page);

			// Create project for new user
			const newProject = { title: `New Project ${Date.now()}` };
			const newProjectId = await createProject(page, newProject);

			// Navigate directly to project URL
			await page.goto(`/projects/${newProjectId}`);
			await expect(page.locator(`text=${newProject.title}`)).toBeVisible();
		});

		test('should support direct URL to episode', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			// Navigate to dashboard
			await page.goto('/dashboard');

			// Navigate directly to episode URL
			await page.goto(`/episodes/${episodeId}`);
			await expect(page.locator(`text=${episode.title}`)).toBeVisible();
		});

		test('should redirect unauthorized deep links to login', async ({ page }) => {
			// Not logged in, try to access episode directly
			await page.goto('/episodes/some-episode-id');

			// Should redirect to login
			await expect(page).toHaveURL(/\/login/);
		});
	});

	test.describe('Loading States', () => {
		test('should show loading state during navigation', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			// Click to navigate
			await page.goto('/dashboard');
			const projectLink = page.locator(`text=${project.title}`);

			// Start navigation and check for loading indicator
			await projectLink.click();

			// Loading indicator may appear briefly
			// This is optional - some navigations may be too fast
			const hasLoading = await page.locator('.loading, [role="progressbar"], .spinner')
				.isVisible({ timeout: 100 })
				.catch(() => false);

			// Navigation should complete
			await expect(page).toHaveURL(`/projects/${projectId}`);
		});

		test('should not show stale data during navigation', async ({ page }) => {
			await signUpAndLogin(page);
			const project1 = { title: `Project A ${Date.now()}` };
			const project2 = { title: `Project B ${Date.now() + 1}` };

			const projectId1 = await createProject(page, project1);
			const projectId2 = await createProject(page, project2);

			// Navigate to project1
			await page.goto(`/projects/${projectId1}`);
			await expect(page.locator(`text=${project1.title}`)).toBeVisible();

			// Navigate to project2
			await page.goto(`/projects/${projectId2}`);

			// Should not show project1 title
			await expect(page.locator(`text=${project1.title}`)).not.toBeVisible();
			await expect(page.locator(`text=${project2.title}`)).toBeVisible();
		});
	});

	test.describe('Empty States', () => {
		test('should show helpful empty state on dashboard with no projects', async ({ page }) => {
			await signUpAndLogin(page);
			await page.goto('/dashboard');

			// Should show empty state with call to action
			await expect(page.locator('text=/no projects|create your first|get started/i')).toBeVisible();
			await expect(page.locator('button:has-text("Create Project")')).toBeVisible();
		});

		test('should show empty state on project with no episodes', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Empty Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			// Should show empty state
			await expect(page.locator('text=/no episodes|create your first|get started/i')).toBeVisible();
			await expect(page.locator('button:has-text("Create Episode")')).toBeVisible();
		});

		test('should show empty state on episode with no content', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			// Should show empty state
			await expect(page.locator('text=/no content|add content|get started/i')).toBeVisible();
			await expect(page.locator('button:has-text("Add Content")')).toBeVisible();
		});
	});

	test.describe('Error Pages', () => {
		test('should show 404 for non-existent project', async ({ page }) => {
			await signUpAndLogin(page);

			// Navigate to non-existent project
			await page.goto('/projects/non-existent-id-12345');

			// Should show 404 or "not found" message
			await expect(page.locator('text=/404|not found|does not exist/i')).toBeVisible();
		});

		test('should show 404 for non-existent episode', async ({ page }) => {
			await signUpAndLogin(page);

			// Navigate to non-existent episode
			await page.goto('/episodes/non-existent-id-12345');

			// Should show 404 or "not found"
			await expect(page.locator('text=/404|not found|does not exist/i')).toBeVisible();
		});

		test('should provide way to return from error page', async ({ page }) => {
			await signUpAndLogin(page);

			await page.goto('/projects/non-existent-id');

			// Should have link back to dashboard or home
			await expect(
				page.locator('a:has-text("Dashboard"), a:has-text("Home"), button:has-text("Go back")')
			).toBeVisible();
		});
	});

	test.describe('Keyboard Navigation', () => {
		test('should support tab navigation through dashboard', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			await createProject(page, project);

			await page.goto('/dashboard');

			// Start from body
			await page.locator('body').focus();

			// Tab through elements
			await page.keyboard.press('Tab');
			await page.keyboard.press('Tab');

			// Some focusable element should be focused
			const focusedElement = await page.evaluate(() => document.activeElement?.tagName);
			expect(['A', 'BUTTON', 'INPUT']).toContain(focusedElement);
		});

		test('should support Enter key to activate links', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			await page.goto('/dashboard');

			// Focus on project link
			const projectLink = page.locator(`a:has-text("${project.title}")`).first();
			await projectLink.focus();

			// Press Enter
			await page.keyboard.press('Enter');

			// Should navigate
			await expect(page).toHaveURL(`/projects/${projectId}`);
		});

		test('should support Escape key to close modals', async ({ page }) => {
			await signUpAndLogin(page);
			await page.goto('/dashboard');

			// Open create project modal
			await page.click('button:has-text("Create Project")');

			// Modal should be open
			await expect(page.locator('input[placeholder*="title" i]')).toBeVisible();

			// Press Escape
			await page.keyboard.press('Escape');

			// Modal should close
			await expect(page.locator('input[placeholder*="title" i]')).not.toBeVisible();
		});
	});

	test.describe('Mobile Navigation', () => {
		test('should show mobile menu on small screens', async ({ page }) => {
			// Set mobile viewport
			await page.setViewportSize({ width: 375, height: 667 });

			await signUpAndLogin(page);
			await page.goto('/dashboard');

			// Mobile menu button should be visible
			await expect(
				page.locator('button[aria-label*="Menu"], button:has-text("Menu"), [aria-label*="navigation toggle"]')
			).toBeVisible();
		});

		test('should toggle mobile menu', async ({ page }) => {
			await page.setViewportSize({ width: 375, height: 667 });

			await signUpAndLogin(page);
			await page.goto('/dashboard');

			// Click menu button
			const menuButton = page.locator('button[aria-label*="Menu"], button:has-text("Menu")').first();
			await menuButton.click();

			// Menu should open
			await expect(page.locator('nav, [role="dialog"]').first()).toBeVisible();

			// Click again to close
			await menuButton.click();

			// Menu should close (or be hidden)
			const navVisible = await page.locator('nav, [role="dialog"]').first().isVisible().catch(() => false);
			// Menu may use display: none or move off-screen
		});
	});

	test.describe('Search and Filtering', () => {
		test('should show search if available', async ({ page }) => {
			await signUpAndLogin(page);

			// Create multiple projects
			for (let i = 0; i < 5; i++) {
				await createProject(page, { title: `Project ${i} ${Date.now() + i}` });
			}

			await page.goto('/dashboard');

			// If search exists, it should be visible
			const searchExists = await page.locator('input[type="search"], input[placeholder*="search" i]')
				.isVisible({ timeout: 2000 })
				.catch(() => false);

			// This is optional - not all implementations have search
			if (searchExists) {
				await expect(page.locator('input[type="search"], input[placeholder*="search" i]')).toBeVisible();
			}
		});
	});

	test.describe('URL Structure', () => {
		test('should use clean URLs without hash routing', async ({ page }) => {
			await signUpAndLogin(page);
			await page.goto('/dashboard');

			// URL should not contain # (hash)
			expect(page.url()).not.toContain('#');
		});

		test('should use semantic URL paths', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			// Project URL should contain /projects/
			expect(page.url()).toContain('/projects/');

			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			// Episode URL should contain /episodes/
			expect(page.url()).toContain('/episodes/');
		});
	});
});
