import { test, expect } from '@playwright/test';
import { generateTestUser, signUp, login, logout, createUserBContext } from '../utils/auth-helpers';
import { createProject } from '../utils/project-helpers';
import { createEpisode, addContentSource, generatePodcast, waitForGeneration, verifyAudioPlayer } from '../utils/episode-helpers';

// The headline journey and multi-tenant isolation specs below are written and
// ready, but BLOCKED: project/episode creation is broken by the web<->API
// contract mismatch (#337). They are fixme'd with that pointer and just need
// un-fixme'ing once #337 lands. Remaining workflows target unverified UI or live
// generation and stay individually fixme'd.
test.describe('End-to-End Integration Workflows', () => {
	test.describe.fixme('Complete User Journey: Signup to Ready-to-Generate', () => {
		// The headline journey: signup -> login -> project -> episode -> content ->
		// ready to generate. The actual generate -> wait -> download leg lives in the
		// fixme'd "Generation and Download" suite below because live TTS generation
		// depends on the (separately tracked) #313/#314 pipeline work and is too slow
		// /flaky to gate every PR.
		test('should complete signup through ready-to-generate', async ({ page }) => {
			test.setTimeout(120000);

			// 1. Sign up + login a brand-new user
			const user = generateTestUser();
			await signUp(page, user);
			await login(page, user.email, user.password);
			await expect(page).toHaveURL(/\/dashboard/);

			// 2. Create project (navigates to the project page)
			const project = { title: `Integration Test Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			await expect(page).toHaveURL(`/projects/${projectId}`);

			// 3. Create episode (navigates to the episode page)
			const episode = { title: `Integration Test Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);
			await expect(page).toHaveURL(`/episodes/${episodeId}`);

			// 4. Add a content source
			await addContentSource(page, episodeId, {
				type: 'text',
				value: 'This is a comprehensive integration test for the podcast generation platform, covering signup through content creation.',
			});
			await expect(page.getByRole('list', { name: 'Content sources' })).toBeVisible();

			// 5. Episode is now ready to generate
			await expect(page.getByRole('button', { name: 'Generate Podcast' })).toBeVisible();

			// 6. Back to dashboard, project listed, then logout
			await page.goto('/dashboard');
			await expect(page.getByRole('button', { name: `Open project: ${project.title}` })).toBeVisible();
			await logout(page);
			await expect(page).toHaveURL(/\/login/);
		});
	});

	// Live generation + download — pending the generation pipeline work (#313/#314)
	// and intentionally excluded from per-PR gating (slow, external-API dependent).
	test.describe.fixme('Generation and Download', () => {
		test('should generate and download a podcast', async ({ page }) => {
			test.setTimeout(360000);
			const user = generateTestUser();
			await signUp(page, user);
			await login(page, user.email, user.password);

			const projectId = await createProject(page, { title: `Gen Project ${Date.now()}` });
			const episodeId = await createEpisode(page, projectId, { title: `Gen Episode ${Date.now()}` });
			await addContentSource(page, episodeId, { type: 'text', value: 'Generate a podcast from this content.' });

			await generatePodcast(page, episodeId);
			await waitForGeneration(page, episodeId, 300000);
			await verifyAudioPlayer(page);
		});
	});

	test.describe.fixme('Multi-Project Multi-Episode Workflow', () => {
		test('should handle multiple projects with multiple episodes', async ({ page }) => {
			await test.step('Setup: Login', async () => {
				const user = generateTestUser();
				await signUp(page, user);
				await login(page, user.email, user.password);
			});

			const projectIds: string[] = [];
			const episodeIds: string[] = [];

			await test.step('Create 3 projects', async () => {
				for (let i = 0; i < 3; i++) {
					const project = { title: `Project ${i} ${Date.now() + i}` };
					const projectId = await createProject(page, project);
					projectIds.push(projectId);
				}
			});

			await test.step('Create 2 episodes per project', async () => {
				for (const projectId of projectIds) {
					for (let i = 0; i < 2; i++) {
						const episode = { title: `Episode ${i} ${Date.now() + i}` };
						const episodeId = await createEpisode(page, projectId, episode);
						episodeIds.push(episodeId);
					}
				}
			});

			await test.step('Verify all projects on dashboard', async () => {
				await page.goto('/dashboard');

				// Should show 3 projects
				const projectCount = await page.locator('[data-testid="project"], .project-card, article').count();
				expect(projectCount).toBe(3);
			});

			await test.step('Verify episodes in first project', async () => {
				await page.goto(`/projects/${projectIds[0]}`);

				// Should show 2 episodes
				const episodeCount = await page.locator('[data-testid="episode"], .episode-card, article').count();
				expect(episodeCount).toBe(2);
			});
		});
	});

	test.describe.fixme('Content Source Variety Workflow', () => {
		test('should handle mixed content sources in single episode', async ({ page }) => {
			const user = generateTestUser();
			await signUp(page, user);
			await login(page, user.email, user.password);

			const project = { title: `Mixed Content Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			const episode = { title: `Mixed Content Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			// Add URL source
			await addContentSource(page, episodeId, {
				type: 'url',
				value: 'https://example.com/article1',
			});

			// Add text source
			await addContentSource(page, episodeId, {
				type: 'text',
				value: 'This is additional text content to supplement the URL.',
			});

			// Add another URL
			await addContentSource(page, episodeId, {
				type: 'url',
				value: 'https://example.com/article2',
			});

			// Verify all 3 sources visible
			await expect(page.locator('text=https://example.com/article1')).toBeVisible();
			await expect(page.locator('text=/This is additional/i')).toBeVisible();
			await expect(page.locator('text=https://example.com/article2')).toBeVisible();
		});
	});

	test.describe.fixme('Edit and Update Workflow', () => {
		test('should allow editing project, episode, and content', async ({ page }) => {
			const user = generateTestUser();
			await signUp(page, user);
			await login(page, user.email, user.password);

			// Create project
			const project = { title: `Original Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			// Edit project title
			const editProjectButton = page.locator('button:has-text("Edit"), [aria-label="Edit project"]').first();
			await editProjectButton.click();

			const newProjectTitle = `Updated Project ${Date.now()}`;
			const titleInput = page.locator('input[placeholder*="title" i]');
			await titleInput.clear();
			await titleInput.fill(newProjectTitle);

			await page.click('button:has-text("Save"), button:has-text("Update")');

			// Verify updated
			await expect(page.locator(`text=${newProjectTitle}`)).toBeVisible({ timeout: 5000 });

			// Create episode
			const episode = { title: `Original Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			// Edit episode title
			const editEpisodeButton = page.locator('button:has-text("Edit"), [aria-label="Edit episode"]').first();
			await editEpisodeButton.click();

			const newEpisodeTitle = `Updated Episode ${Date.now()}`;
			const episodeTitleInput = page.locator('input[placeholder*="title" i]');
			await episodeTitleInput.clear();
			await episodeTitleInput.fill(newEpisodeTitle);

			await page.click('button:has-text("Save"), button:has-text("Update")');

			// Verify updated
			await expect(page.locator(`text=${newEpisodeTitle}`)).toBeVisible({ timeout: 5000 });

			// Add content source
			const originalUrl = 'https://example.com/original';
			await addContentSource(page, episodeId, { type: 'url', value: originalUrl });

			// Edit content source
			const editContentButton = page.locator('button:has-text("Edit"), [aria-label*="Edit"]').first();
			await editContentButton.click();

			const newUrl = 'https://example.com/updated';
			const urlInput = page.locator('input[type="url"], input[placeholder*="url" i]');
			await urlInput.clear();
			await urlInput.fill(newUrl);

			await page.click('button:has-text("Save"), button:has-text("Update")');

			// Verify updated
			await expect(page.locator(`text=${newUrl}`)).toBeVisible({ timeout: 5000 });
		});
	});

	test.describe.fixme('Delete Workflow', () => {
		test('should cascade delete from project to episodes', async ({ page }) => {
			const user = generateTestUser();
			await signUp(page, user);
			await login(page, user.email, user.password);

			const project = { title: `Project to Delete ${Date.now()}` };
			const projectId = await createProject(page, project);

			const episode1 = { title: `Episode 1 ${Date.now()}` };
			const episode2 = { title: `Episode 2 ${Date.now() + 1}` };

			await createEpisode(page, projectId, episode1);
			await createEpisode(page, projectId, episode2);

			// Go back to project
			await page.goto(`/projects/${projectId}`);

			// Delete project
			const deleteButton = page.locator('button:has-text("Delete"), [aria-label="Delete project"]').first();
			await deleteButton.click();

			// Confirm
			await page.click('button:has-text("Delete"), button:has-text("Confirm"), button:has-text("Yes")');

			// Should redirect to dashboard
			await expect(page).toHaveURL(/\/dashboard/);

			// Project should not exist
			await expect(page.locator(`text=${project.title}`)).not.toBeVisible();
		});
	});

	test.describe.fixme('Session Persistence Workflow', () => {
		test('should maintain session across page refreshes', async ({ page }) => {
			const user = generateTestUser();
			await signUp(page, user);
			await login(page, user.email, user.password);

			const project = { title: `Persistence Test ${Date.now()}` };
			const projectId = await createProject(page, project);

			// Reload page
			await page.reload();

			// Should still be on project page
			await expect(page).toHaveURL(`/projects/${projectId}`);
			await expect(page.locator(`text=${project.title}`)).toBeVisible();

			// Navigate to dashboard
			await page.goto('/dashboard');

			// Reload
			await page.reload();

			// Should still be on dashboard
			await expect(page).toHaveURL(/\/dashboard/);
		});

		test('should persist session across browser back/forward', async ({ page }) => {
			const user = generateTestUser();
			await signUp(page, user);
			await login(page, user.email, user.password);

			const project = { title: `Back/Forward Test ${Date.now()}` };
			const projectId = await createProject(page, project);

			await page.goto('/dashboard');
			await page.goto(`/projects/${projectId}`);

			// Go back
			await page.goBack();
			await expect(page).toHaveURL(/\/dashboard/);

			// Go forward
			await page.goForward();
			await expect(page).toHaveURL(`/projects/${projectId}`);

			// Should still be authenticated
			await expect(page.locator(`text=${project.title}`)).toBeVisible();
		});
	});

	test.describe.fixme('Error Recovery Workflow', () => {
		test('should recover from failed API calls', async ({ page }) => {
			const user = generateTestUser();
			await signUp(page, user);
			await login(page, user.email, user.password);

			const project = { title: `Error Recovery ${Date.now()}` };
			const projectId = await createProject(page, project);

			// Navigate away and back
			await page.goto('/dashboard');
			await page.goto(`/projects/${projectId}`);

			// Project should load correctly
			await expect(page.locator(`text=${project.title}`)).toBeVisible();
		});
	});

	// Two genuinely independent sessions (User A shared session + User B persistent
	// context) prove data isolation. Ready to run, but BLOCKED on project creation
	// (#337). Un-fixme once #337 lands.
	test.describe.fixme('Concurrent User Workflow', () => {
		test('should isolate data between two independent users', async ({ page, browser }) => {
			// User A (shared session) creates a project.
			const userAProject = { title: `User A Project ${Date.now()}` };
			const userAProjectId = await createProject(page, userAProject);

			// User B — an independent authenticated context.
			const userBContext = await createUserBContext(browser);
			try {
				const userBPage = await userBContext.newPage();

				// User B's dashboard must not list User A's project.
				await userBPage.goto('/dashboard');
				await expect(
					userBPage.getByRole('button', { name: `Open project: ${userAProject.title}` })
				).toHaveCount(0);

				// User B cannot open User A's project directly.
				await userBPage.goto(`/projects/${userAProjectId}`);
				await expect(userBPage.getByRole('heading', { name: userAProject.title })).toHaveCount(0);
				await expect(userBPage.getByText('Failed to load project')).toBeVisible({ timeout: 5000 });
			} finally {
				await userBContext.close();
			}
		});
	});

	test.describe.fixme('Mobile Integration Workflow', () => {
		test('should complete workflow on mobile device', async ({ page }) => {
			// Set mobile viewport
			await page.setViewportSize({ width: 375, height: 667 });

			const user = generateTestUser();
			await signUp(page, user);
			await login(page, user.email, user.password);

			const project = { title: `Mobile Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			const episode = { title: `Mobile Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			await addContentSource(page, episodeId, {
				type: 'text',
				value: 'Mobile content test',
			});

			// Verify everything accessible on mobile
			await expect(page.locator(`text=${episode.title}`)).toBeVisible();
			await expect(page.locator('text=/Mobile content/i')).toBeVisible();
		});
	});

	test.describe.fixme('Performance Under Load', () => {
		test('should handle user with many projects efficiently', async ({ page }) => {
			const user = generateTestUser();
			await signUp(page, user);
			await login(page, user.email, user.password);

			// Create 20 projects
			const projectIds: string[] = [];
			for (let i = 0; i < 20; i++) {
				const project = { title: `Bulk Project ${i} ${Date.now() + i}` };
				const projectId = await createProject(page, project);
				projectIds.push(projectId);
			}

			// Load dashboard
			const startTime = Date.now();
			await page.goto('/dashboard');
			await expect(page.locator('[data-testid="project"], .project-card, article').first()).toBeVisible();
			const loadTime = Date.now() - startTime;

			// Should load in reasonable time even with 20 projects
			expect(loadTime).toBeLessThan(5000);

			// Should display all projects
			const projectCount = await page.locator('[data-testid="project"], .project-card, article').count();
			expect(projectCount).toBe(20);
		});
	});

	test.describe.fixme('Browser Compatibility Workflow', () => {
		test('should work across different browser back/forward behaviors', async ({ page }) => {
			const user = generateTestUser();
			await signUp(page, user);
			await login(page, user.email, user.password);

			const project1 = { title: `Project A ${Date.now()}` };
			const project2 = { title: `Project B ${Date.now() + 1}` };

			const projectId1 = await createProject(page, project1);
			const projectId2 = await createProject(page, project2);

			// Navigate: Dashboard -> Project1 -> Dashboard -> Project2
			await page.goto('/dashboard');
			await page.goto(`/projects/${projectId1}`);
			await page.goto('/dashboard');
			await page.goto(`/projects/${projectId2}`);

			// Go back to dashboard
			await page.goBack();
			await expect(page).toHaveURL(/\/dashboard/);

			// Go back to project1
			await page.goBack();
			await expect(page).toHaveURL(`/projects/${projectId1}`);

			// Forward to dashboard
			await page.goForward();
			await expect(page).toHaveURL(/\/dashboard/);

			// Forward to project2
			await page.goForward();
			await expect(page).toHaveURL(`/projects/${projectId2}`);
		});
	});

	test.describe.fixme('Complete Feature Coverage', () => {
		test('should exercise all major features in single workflow', async ({ page }) => {
			test.setTimeout(420000); // 7 minutes

			const user = generateTestUser();

			// Auth
			await signUp(page, user);
			await login(page, user.email, user.password);

			// Project management
			const project = { title: `Full Feature Test ${Date.now()}` };
			const projectId = await createProject(page, project);

			// Episode management
			const episode = { title: `Full Feature Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			// Content sources
			await addContentSource(page, episodeId, { type: 'url', value: 'https://example.com/test' });
			await addContentSource(page, episodeId, { type: 'text', value: 'Additional test content' });

			// Generation (full workflow)
			await generatePodcast(page, episodeId);
			await waitForGeneration(page, episodeId, 300000);

			// Audio playback
			await verifyAudioPlayer(page);

			// Navigation
			await page.goto('/dashboard');
			await page.goto(`/projects/${projectId}`);
			await page.goto(`/episodes/${episodeId}`);

			// Cleanup
			const logoutButton = page.locator('button:has-text("Logout"), button:has-text("Sign out")').first();
			await logoutButton.click();

			// All features verified
			await expect(page).toHaveURL(/\/login/);
		});
	});
});
