import { test, expect } from '@playwright/test';
import { signUpAndLogin } from '../utils/auth-helpers';
import { createProject } from '../utils/project-helpers';
import { createEpisode, addContentSource, generatePodcast, waitForGeneration, verifyAudioPlayer } from '../utils/episode-helpers';

test.describe('Podcast Generation', () => {
	test.describe('Start Generation', () => {
		test('should display generate button when content exists', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			// Add content
			await addContentSource(page, episodeId, {
				type: 'text',
				value: 'Sample content for podcast generation',
			});

			// Generate button should be visible
			await expect(page.locator('button:has-text("Generate"), button:has-text("Generate Podcast")')).toBeVisible();
		});

		test('should start podcast generation with URL content', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			await addContentSource(page, episodeId, {
				type: 'url',
				value: 'https://example.com/article',
			});

			await generatePodcast(page, episodeId);

			// Should show generating status
			await expect(page.locator('text=/generating|in progress|processing/i')).toBeVisible({ timeout: 10000 });
		});

		test('should start podcast generation with text content', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			await addContentSource(page, episodeId, {
				type: 'text',
				value: 'This is sample text content that will be converted into a podcast conversation.',
			});

			await generatePodcast(page, episodeId);

			// Should show generating status
			await expect(page.locator('text=/generating|in progress|processing/i')).toBeVisible({ timeout: 10000 });
		});

		test('should start generation with mixed content sources', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			// Add multiple sources
			await addContentSource(page, episodeId, { type: 'url', value: 'https://example.com/1' });
			await addContentSource(page, episodeId, { type: 'text', value: 'Additional context' });

			await generatePodcast(page, episodeId);

			// Should show generating
			await expect(page.locator('text=/generating|in progress/i')).toBeVisible({ timeout: 10000 });
		});

		test('should prevent generation while already generating', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			await addContentSource(page, episodeId, {
				type: 'text',
				value: 'Content for generation test',
			});

			await generatePodcast(page, episodeId);

			// Wait for generation to start
			await page.waitForTimeout(2000);

			// Generate button should be disabled or hidden
			const generateButton = page.locator('button:has-text("Generate"), button:has-text("Generate Podcast")');
			const isDisabled = await generateButton.isDisabled().catch(() => true);
			const isHidden = !(await generateButton.isVisible().catch(() => false));

			expect(isDisabled || isHidden).toBe(true);
		});
	});

	test.describe('Generation Progress', () => {
		test('should show progress indicator during generation', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			await addContentSource(page, episodeId, {
				type: 'text',
				value: 'Content for progress test',
			});

			await generatePodcast(page, episodeId);

			// Should show progress indicator (spinner, bar, percentage, etc.)
			await expect(
				page.locator('[role="progressbar"], [aria-label*="progress"], .spinner, .loading')
			).toBeVisible({ timeout: 10000 });
		});

		test('should show status updates during generation', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			await addContentSource(page, episodeId, {
				type: 'text',
				value: 'Content for status updates test',
			});

			await generatePodcast(page, episodeId);

			// Should show status like "Extracting content", "Generating transcript", etc.
			await expect(
				page.locator('text=/extracting|generating|processing|converting/i')
			).toBeVisible({ timeout: 10000 });
		});

		test('should update progress percentage', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			await addContentSource(page, episodeId, {
				type: 'text',
				value: 'Content for percentage test',
			});

			await generatePodcast(page, episodeId);

			// Should show percentage (0%, 25%, 50%, etc.)
			await expect(page.locator('text=/%|percent/i')).toBeVisible({ timeout: 10000 });
		});
	});

	test.describe('Generation Completion', () => {
		test('should show completion status', async ({ page }) => {
			test.setTimeout(300000); // 5 minutes for generation

			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			await addContentSource(page, episodeId, {
				type: 'text',
				value: 'Short content for quick completion test',
			});

			await generatePodcast(page, episodeId);
			await waitForGeneration(page, episodeId);

			// Should show completed status
			await expect(page.locator('text=/complete|completed|success|ready/i')).toBeVisible();
		});

		test('should display audio player after generation', async ({ page }) => {
			test.setTimeout(300000);

			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			await addContentSource(page, episodeId, {
				type: 'text',
				value: 'Content for audio player test',
			});

			await generatePodcast(page, episodeId);
			await waitForGeneration(page, episodeId);

			// Verify audio player
			await verifyAudioPlayer(page);
		});

		test('should enable download after generation', async ({ page }) => {
			test.setTimeout(300000);

			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			await addContentSource(page, episodeId, {
				type: 'text',
				value: 'Content for download test',
			});

			await generatePodcast(page, episodeId);
			await waitForGeneration(page, episodeId);

			// Download button should be visible
			await expect(page.locator('button:has-text("Download"), a:has-text("Download")')).toBeVisible();
		});

		test('should show audio duration', async ({ page }) => {
			test.setTimeout(300000);

			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			await addContentSource(page, episodeId, {
				type: 'text',
				value: 'Content for duration test',
			});

			await generatePodcast(page, episodeId);
			await waitForGeneration(page, episodeId);

			// Should show duration like "2:34" or "5 minutes"
			await expect(page.locator('text=/\\d+:\\d+|\\d+\\s*min/i')).toBeVisible();
		});
	});

	test.describe('Generation Errors', () => {
		test('should handle invalid URL gracefully', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			// Add invalid URL
			await addContentSource(page, episodeId, {
				type: 'url',
				value: 'https://this-domain-definitely-does-not-exist-12345.com',
			});

			await generatePodcast(page, episodeId);

			// Should show error message
			await expect(
				page.locator('text=/error|failed|could not|unable/i')
			).toBeVisible({ timeout: 60000 });
		});

		test('should show error for insufficient content', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			// Add very short content
			await addContentSource(page, episodeId, {
				type: 'text',
				value: 'Too short',
			});

			await generatePodcast(page, episodeId);

			// Should show error or warning
			await expect(
				page.locator('text=/error|insufficient|too short|need more/i')
			).toBeVisible({ timeout: 60000 });
		});

		test('should allow retry after error', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			await addContentSource(page, episodeId, {
				type: 'url',
				value: 'https://invalid-url-for-retry.test',
			});

			await generatePodcast(page, episodeId);

			// Wait for error
			await expect(page.locator('text=/error|failed/i')).toBeVisible({ timeout: 60000 });

			// Retry button should be available
			await expect(
				page.locator('button:has-text("Retry"), button:has-text("Try Again")')
			).toBeVisible();
		});
	});

	test.describe('Audio Player', () => {
		test('should play audio', async ({ page }) => {
			test.setTimeout(300000);

			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			await addContentSource(page, episodeId, {
				type: 'text',
				value: 'Content for playback test',
			});

			await generatePodcast(page, episodeId);
			await waitForGeneration(page, episodeId);

			// Click play button
			const playButton = page.locator('button[aria-label*="Play"], button:has-text("Play")').first();
			await playButton.click();

			// Audio should be playing (button changes to pause)
			await expect(
				page.locator('button[aria-label*="Pause"], button:has-text("Pause")')
			).toBeVisible({ timeout: 5000 });
		});

		test('should pause audio', async ({ page }) => {
			test.setTimeout(300000);

			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			await addContentSource(page, episodeId, {
				type: 'text',
				value: 'Content for pause test',
			});

			await generatePodcast(page, episodeId);
			await waitForGeneration(page, episodeId);

			// Play
			const playButton = page.locator('button[aria-label*="Play"], button:has-text("Play")').first();
			await playButton.click();

			// Wait for playback to start
			await page.waitForTimeout(1000);

			// Pause
			const pauseButton = page.locator('button[aria-label*="Pause"], button:has-text("Pause")').first();
			await pauseButton.click();

			// Should show play button again
			await expect(
				page.locator('button[aria-label*="Play"], button:has-text("Play")')
			).toBeVisible({ timeout: 5000 });
		});

		test('should show playback controls', async ({ page }) => {
			test.setTimeout(300000);

			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			await addContentSource(page, episodeId, {
				type: 'text',
				value: 'Content for controls test',
			});

			await generatePodcast(page, episodeId);
			await waitForGeneration(page, episodeId);

			// Verify controls exist
			await expect(page.locator('audio, [role="region"][aria-label*="audio"]')).toBeVisible();
			await expect(page.locator('button[aria-label*="Play"]')).toBeVisible();
		});
	});

	test.describe('Download Podcast', () => {
		test('should download generated podcast', async ({ page }) => {
			test.setTimeout(300000);

			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			await addContentSource(page, episodeId, {
				type: 'text',
				value: 'Content for download test',
			});

			await generatePodcast(page, episodeId);
			await waitForGeneration(page, episodeId);

			// Set up download listener
			const downloadPromise = page.waitForEvent('download');

			// Click download
			await page.click('button:has-text("Download"), a:has-text("Download")');

			// Verify download started
			const download = await downloadPromise;
			expect(download.suggestedFilename()).toMatch(/\.mp3|\.wav|\.m4a/i);
		});
	});

	test.describe('Regeneration', () => {
		test('should allow regeneration of podcast', async ({ page }) => {
			test.setTimeout(600000); // 10 minutes for two generations

			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			await addContentSource(page, episodeId, {
				type: 'text',
				value: 'Content for regeneration test',
			});

			// First generation
			await generatePodcast(page, episodeId);
			await waitForGeneration(page, episodeId);

			// Regenerate button should be available
			const regenerateButton = page.locator('button:has-text("Regenerate"), button:has-text("Generate Again")');
			await expect(regenerateButton).toBeVisible();

			// Start regeneration
			await regenerateButton.click();

			// Should start generating again
			await expect(page.locator('text=/generating|in progress/i')).toBeVisible({ timeout: 10000 });
		});
	});

	test.describe('Generation History', () => {
		test('should show generation timestamp', async ({ page }) => {
			test.setTimeout(300000);

			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			await addContentSource(page, episodeId, {
				type: 'text',
				value: 'Content for timestamp test',
			});

			await generatePodcast(page, episodeId);
			await waitForGeneration(page, episodeId);

			// Should show when generated (e.g., "Generated 2 minutes ago")
			await expect(
				page.locator('text=/generated|created|\\d+\\s*(second|minute|hour)s?\\s*ago/i')
			).toBeVisible();
		});
	});
});
