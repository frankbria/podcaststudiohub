import { test, expect } from '@playwright/test';
import { signUpAndLogin } from '../utils/auth-helpers';
import { createProject } from '../utils/project-helpers';
import { createEpisode } from '../utils/episode-helpers';

test.describe('Episode Management', () => {
	test.describe('Create Episode', () => {
		test('should display create episode button on project page', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Test Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			await expect(page.locator('button:has-text("Create Episode")')).toBeVisible();
		});

		test('should create episode with title only', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			// Should navigate to episode page
			await expect(page).toHaveURL(`/episodes/${episodeId}`);
			await expect(page.locator(`text=${episode.title}`)).toBeVisible();
		});

		test('should create episode with title and description', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			const episode = {
				title: `Episode ${Date.now()}`,
				description: 'This is a test episode description',
			};

			// Navigate to project
			await page.goto(`/projects/${projectId}`);
			await page.click('button:has-text("Create Episode")');

			// Fill form
			await page.fill('input[placeholder*="title" i], input[placeholder*="episode" i]', episode.title);

			const descField = page.locator('input[placeholder*="description" i], textarea').first();
			if (await descField.isVisible({ timeout: 1000 }).catch(() => false)) {
				await descField.fill(episode.description);
			}

			await page.click('button:has-text("Create Episode"), button:has-text("Create")');

			// Verify
			await expect(page).toHaveURL(/\/episodes\/[a-f0-9-]+/);
			await expect(page.locator(`text=${episode.title}`)).toBeVisible();
		});

		test('should show validation error for empty title', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			await page.click('button:has-text("Create Episode")');

			// Try to submit empty form
			const submitButton = page.locator('button:has-text("Create Episode"), button:has-text("Create")').last();
			await submitButton.click();

			// Should show validation
			const titleInput = page.locator('input[placeholder*="title" i], input[placeholder*="episode" i]');
			await expect(titleInput).toHaveAttribute('required', '');
		});

		test('should create multiple episodes in project', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			const episode1 = { title: `Episode 1 ${Date.now()}` };
			const episode2 = { title: `Episode 2 ${Date.now() + 1}` };

			await createEpisode(page, projectId, episode1);
			await createEpisode(page, projectId, episode2);

			// Navigate to project and verify both episodes exist
			await page.goto(`/projects/${projectId}`);
			await expect(page.locator(`text=${episode1.title}`)).toBeVisible();
			await expect(page.locator(`text=${episode2.title}`)).toBeVisible();
		});
	});

	test.describe('View Episode', () => {
		test('should display episode details', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			const episode = {
				title: `View Test ${Date.now()}`,
			};
			const episodeId = await createEpisode(page, projectId, episode);

			// Verify episode page elements
			await expect(page.locator(`text=${episode.title}`)).toBeVisible();
			await expect(page.locator('button:has-text("Add Content")')).toBeVisible();
		});

		test('should display empty state when no content sources', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			const episode = { title: `Empty Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			// Should show empty state
			await expect(
				page.locator('text=/no content|add content|get started/i')
			).toBeVisible();
		});

		test('should navigate to episode from project page', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			const episode = { title: `Nav Test ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			// Go back to project
			await page.goto(`/projects/${projectId}`);

			// Click episode
			await page.click(`text=${episode.title}`);

			await expect(page).toHaveURL(`/episodes/${episodeId}`);
		});
	});

	test.describe('Edit Episode', () => {
		test('should update episode title', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			const episode = { title: `Original ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			// Edit episode
			const editButton = page.locator('button:has-text("Edit"), [aria-label="Edit episode"]').first();
			await editButton.click();

			const newTitle = `Updated ${Date.now()}`;
			const titleInput = page.locator('input[placeholder*="title" i]');
			await titleInput.clear();
			await titleInput.fill(newTitle);

			await page.click('button:has-text("Save"), button:has-text("Update")');

			// Verify
			await expect(page.locator(`text=${newTitle}`)).toBeVisible({ timeout: 5000 });
		});

		test('should update episode description', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			const episode = { title: `Desc Test ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			// Edit
			const editButton = page.locator('button:has-text("Edit"), [aria-label="Edit episode"]').first();
			await editButton.click();

			const newDesc = 'Updated description';
			const descInput = page.locator('input[placeholder*="description" i], textarea').first();
			await descInput.clear();
			await descInput.fill(newDesc);

			await page.click('button:has-text("Save"), button:has-text("Update")');

			// Verify
			await expect(page.locator(`text=${newDesc}`)).toBeVisible({ timeout: 5000 });
		});
	});

	test.describe('Delete Episode', () => {
		test('should delete episode', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			const episode = { title: `Delete Test ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			// Delete episode
			const deleteButton = page.locator('button:has-text("Delete"), [aria-label="Delete episode"]').first();
			await deleteButton.click();

			// Confirm deletion
			await page.click('button:has-text("Delete"), button:has-text("Confirm"), button:has-text("Yes")');

			// Should redirect to project
			await expect(page).toHaveURL(`/projects/${projectId}`);

			// Verify episode gone
			await expect(page.locator(`text=${episode.title}`)).not.toBeVisible();
		});

		test('should show confirmation dialog before delete', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			const episode = { title: `Confirm Delete ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			// Click delete
			const deleteButton = page.locator('button:has-text("Delete"), [aria-label="Delete episode"]').first();
			await deleteButton.click();

			// Should show confirmation
			await expect(
				page.locator('text=/are you sure|confirm|delete this episode/i')
			).toBeVisible({ timeout: 5000 });
		});

		test('should cancel delete operation', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			const episode = { title: `Cancel Delete ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			// Click delete
			const deleteButton = page.locator('button:has-text("Delete"), [aria-label="Delete episode"]').first();
			await deleteButton.click();

			// Cancel
			await page.click('button:has-text("Cancel"), button:has-text("No")');

			// Should still be on episode page
			await expect(page).toHaveURL(`/episodes/${episodeId}`);
			await expect(page.locator(`text=${episode.title}`)).toBeVisible();
		});
	});

	test.describe('Episode List in Project', () => {
		test('should display all episodes in project', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			// Create multiple episodes
			const episodes = [
				{ title: `Episode 1 ${Date.now()}` },
				{ title: `Episode 2 ${Date.now() + 1}` },
				{ title: `Episode 3 ${Date.now() + 2}` },
			];

			for (const episode of episodes) {
				await createEpisode(page, projectId, episode);
			}

			// Go to project and verify all visible
			await page.goto(`/projects/${projectId}`);
			for (const episode of episodes) {
				await expect(page.locator(`text=${episode.title}`)).toBeVisible();
			}
		});

		test('should show episode count in project', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			// Create 3 episodes
			for (let i = 0; i < 3; i++) {
				await createEpisode(page, projectId, { title: `Episode ${i} ${Date.now() + i}` });
			}

			// Go to project
			await page.goto(`/projects/${projectId}`);

			// Should show count (may be "3 episodes" or similar)
			await expect(page.locator('text=/3.*episode|episode.*3/i')).toBeVisible();
		});
	});

	test.describe('Episode Access Control', () => {
		test('should not allow access to other user episodes', async ({ page }) => {
			// User A creates episode
			const userA = await signUpAndLogin(page);
			const project = { title: `Private Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Private Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			// Logout
			await page.goto('/dashboard');
			const logoutButton = page.locator('button:has-text("Logout"), button:has-text("Sign out")').first();
			await logoutButton.click();

			// User B tries to access
			await signUpAndLogin(page);
			await page.goto(`/episodes/${episodeId}`);

			// Should show error
			await expect(
				page.locator('text=/not found|access denied|unauthorized|forbidden/i')
			).toBeVisible({ timeout: 5000 });
		});
	});

	test.describe('Episode Navigation', () => {
		test('should navigate back to project from episode', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			// Find and click back/project link
			const backLink = page.locator(`a:has-text("${project.title}"), a:has-text("Back"), [aria-label="Back to project"]`).first();
			await backLink.click();

			await expect(page).toHaveURL(`/projects/${projectId}`);
		});

		test('should show breadcrumb navigation', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Breadcrumb Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Breadcrumb Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			// Check breadcrumb contains both project and episode
			const breadcrumb = page.locator('[aria-label="Breadcrumb"], nav').first();
			await expect(breadcrumb.locator(`text=${project.title}`)).toBeVisible();
			await expect(breadcrumb.locator(`text=${episode.title}`)).toBeVisible();
		});
	});

	test.describe('Episode Status', () => {
		test('should show draft status for new episode', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Draft Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			// Should show draft status
			await expect(page.locator('text=/draft|not generated|pending/i')).toBeVisible();
		});
	});
});
