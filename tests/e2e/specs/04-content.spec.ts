import { test, expect } from '@playwright/test';
import { signUpAndLogin } from '../utils/auth-helpers';
import { createProject } from '../utils/project-helpers';
import { createEpisode, addContentSource, deleteContentSource } from '../utils/episode-helpers';

test.describe('Content Source Management', () => {
	test.describe('Add URL Content', () => {
		test('should display add content button', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			await expect(page.locator('button:has-text("Add Content")')).toBeVisible();
		});

		test('should add URL content source', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			const contentSource = {
				type: 'url' as const,
				value: 'https://example.com/article',
			};

			await addContentSource(page, episodeId, contentSource);

			// Verify content source appears
			await expect(page.locator(`text=${contentSource.value}`)).toBeVisible();
		});

		test('should validate URL format', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			await page.click('button:has-text("Add Content")');

			// Try to add invalid URL
			const urlInput = page.locator('input[type="url"], input[placeholder*="url" i]');
			await urlInput.fill('not-a-valid-url');

			const submitButton = page.locator('button:has-text("Add Content"), button:has-text("Add")').last();
			await submitButton.click();

			// Should show validation error or prevent submission
			await expect(urlInput).toHaveAttribute('type', 'url');
		});

		test('should add multiple URL sources', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			const urls = [
				{ type: 'url' as const, value: 'https://example.com/article1' },
				{ type: 'url' as const, value: 'https://example.com/article2' },
				{ type: 'url' as const, value: 'https://example.com/article3' },
			];

			for (const url of urls) {
				await addContentSource(page, episodeId, url);
			}

			// Verify all URLs visible
			for (const url of urls) {
				await expect(page.locator(`text=${url.value}`)).toBeVisible();
			}
		});

		test('should add YouTube URL', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			const youtubeUrl = {
				type: 'url' as const,
				value: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
			};

			await addContentSource(page, episodeId, youtubeUrl);

			// Verify YouTube URL appears
			await expect(page.locator(`text=/youtube|${youtubeUrl.value}/i`)).toBeVisible();
		});
	});

	test.describe('Add Text Content', () => {
		test('should add text content source', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			const textContent = {
				type: 'text' as const,
				value: 'This is sample text content for the podcast generation.',
			};

			await addContentSource(page, episodeId, textContent);

			// Verify text content appears (may be truncated in display)
			await expect(page.locator(`text=/This is sample text/i`)).toBeVisible();
		});

		test('should validate text content not empty', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			await page.click('button:has-text("Add Content")');

			// Switch to text tab
			const textButton = page.locator('button:has-text("Text"), [role="tab"]:has-text("Text")').first();
			if (await textButton.isVisible({ timeout: 1000 }).catch(() => false)) {
				await textButton.click();
			}

			// Try to submit empty text
			const submitButton = page.locator('button:has-text("Add Content"), button:has-text("Add")').last();
			await submitButton.click();

			// Should show validation
			const textArea = page.locator('textarea, input[placeholder*="text" i]');
			await expect(textArea).toHaveAttribute('required', '');
		});

		test('should add long text content', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			const longText = {
				type: 'text' as const,
				value: 'Lorem ipsum dolor sit amet, '.repeat(100), // Long text
			};

			await addContentSource(page, episodeId, longText);

			// Verify text was added (may be truncated in display)
			await expect(page.locator('text=/Lorem ipsum/i')).toBeVisible();
		});

		test('should add multiple text sources', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			const textSources = [
				{ type: 'text' as const, value: 'First text content about AI.' },
				{ type: 'text' as const, value: 'Second text content about ML.' },
			];

			for (const text of textSources) {
				await addContentSource(page, episodeId, text);
			}

			// Verify both texts visible
			await expect(page.locator('text=/First text content/i')).toBeVisible();
			await expect(page.locator('text=/Second text content/i')).toBeVisible();
		});
	});

	test.describe('Mixed Content Sources', () => {
		test('should add both URL and text sources', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			// Add URL
			await addContentSource(page, episodeId, {
				type: 'url',
				value: 'https://example.com/article',
			});

			// Add text
			await addContentSource(page, episodeId, {
				type: 'text',
				value: 'Additional context text',
			});

			// Verify both visible
			await expect(page.locator('text=https://example.com/article')).toBeVisible();
			await expect(page.locator('text=/Additional context/i')).toBeVisible();
		});

		test('should show content source count', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			// Add 3 sources
			await addContentSource(page, episodeId, { type: 'url', value: 'https://example.com/1' });
			await addContentSource(page, episodeId, { type: 'url', value: 'https://example.com/2' });
			await addContentSource(page, episodeId, { type: 'text', value: 'Some text content' });

			// Should show count (may be "3 sources" or similar)
			await expect(page.locator('text=/3.*source|source.*3/i')).toBeVisible();
		});
	});

	test.describe('Edit Content Source', () => {
		test('should edit URL content source', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			// Add initial URL
			await addContentSource(page, episodeId, {
				type: 'url',
				value: 'https://example.com/original',
			});

			// Edit content source
			const editButton = page.locator('button:has-text("Edit"), [aria-label*="Edit"]').first();
			await editButton.click();

			const newUrl = 'https://example.com/updated';
			const urlInput = page.locator('input[type="url"], input[placeholder*="url" i]');
			await urlInput.clear();
			await urlInput.fill(newUrl);

			await page.click('button:has-text("Save"), button:has-text("Update")');

			// Verify updated URL
			await expect(page.locator(`text=${newUrl}`)).toBeVisible({ timeout: 5000 });
		});

		test('should edit text content source', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			// Add initial text
			await addContentSource(page, episodeId, {
				type: 'text',
				value: 'Original text content',
			});

			// Edit
			const editButton = page.locator('button:has-text("Edit"), [aria-label*="Edit"]').first();
			await editButton.click();

			const newText = 'Updated text content';
			const textArea = page.locator('textarea, input[placeholder*="text" i]');
			await textArea.clear();
			await textArea.fill(newText);

			await page.click('button:has-text("Save"), button:has-text("Update")');

			// Verify
			await expect(page.locator(`text=/Updated text content/i`)).toBeVisible({ timeout: 5000 });
		});
	});

	test.describe('Delete Content Source', () => {
		test('should delete URL content source', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			const url = 'https://example.com/to-delete';
			await addContentSource(page, episodeId, { type: 'url', value: url });

			// Delete
			await deleteContentSource(page, 0);

			// Verify removed
			await expect(page.locator(`text=${url}`)).not.toBeVisible();
		});

		test('should delete text content source', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			await addContentSource(page, episodeId, {
				type: 'text',
				value: 'Text to delete',
			});

			// Delete
			await deleteContentSource(page, 0);

			// Verify removed
			await expect(page.locator('text=/Text to delete/i')).not.toBeVisible();
		});

		test('should show confirmation before delete', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			await addContentSource(page, episodeId, { type: 'url', value: 'https://example.com' });

			// Click delete
			const deleteButton = page.locator('button:has-text("Delete"), [aria-label*="Delete"]').first();
			await deleteButton.click();

			// Should show confirmation
			await expect(
				page.locator('text=/are you sure|confirm|delete this content/i')
			).toBeVisible({ timeout: 5000 });
		});

		test('should cancel delete operation', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			const url = 'https://example.com/keep-me';
			await addContentSource(page, episodeId, { type: 'url', value: url });

			// Click delete
			const deleteButton = page.locator('button:has-text("Delete"), [aria-label*="Delete"]').first();
			await deleteButton.click();

			// Cancel
			await page.click('button:has-text("Cancel"), button:has-text("No")');

			// Should still exist
			await expect(page.locator(`text=${url}`)).toBeVisible();
		});

		test('should delete specific source from multiple', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			// Add 3 sources
			await addContentSource(page, episodeId, { type: 'url', value: 'https://example.com/1' });
			await addContentSource(page, episodeId, { type: 'url', value: 'https://example.com/2' });
			await addContentSource(page, episodeId, { type: 'url', value: 'https://example.com/3' });

			// Delete middle one
			await deleteContentSource(page, 1);

			// Verify only middle one removed
			await expect(page.locator('text=https://example.com/1')).toBeVisible();
			await expect(page.locator('text=https://example.com/2')).not.toBeVisible();
			await expect(page.locator('text=https://example.com/3')).toBeVisible();
		});
	});

	test.describe('Content Source Display', () => {
		test('should show content type indicator', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			await addContentSource(page, episodeId, { type: 'url', value: 'https://example.com' });

			// Should show URL indicator/icon
			await expect(page.locator('[aria-label*="URL"], text=/URL|Link/i')).toBeVisible();
		});

		test('should truncate long URLs in display', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			const longUrl = 'https://example.com/very/long/path/that/should/be/truncated/in/the/display';
			await addContentSource(page, episodeId, { type: 'url', value: longUrl });

			// URL should be visible (may be truncated)
			await expect(page.locator('text=/example.com/i')).toBeVisible();
		});

		test('should show text preview', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			const longText = 'This is a very long text content that should be truncated in the preview display';
			await addContentSource(page, episodeId, { type: 'text', value: longText });

			// Should show preview (likely truncated)
			await expect(page.locator('text=/This is a very long/i')).toBeVisible();
		});
	});

	test.describe('Content Source Validation', () => {
		test('should prevent duplicate URLs', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			const url = 'https://example.com/duplicate';

			// Add URL first time
			await addContentSource(page, episodeId, { type: 'url', value: url });

			// Try to add same URL again
			await page.click('button:has-text("Add Content")');
			await page.fill('input[type="url"], input[placeholder*="url" i]', url);
			await page.click('button:has-text("Add Content"), button:has-text("Add")');

			// Should show error about duplicate
			await expect(page.locator('text=/duplicate|already|exists/i')).toBeVisible({ timeout: 5000 });
		});

		test('should require at least one content source for generation', async ({ page }) => {
			await signUpAndLogin(page);
			const project = { title: `Project ${Date.now()}` };
			const projectId = await createProject(page, project);
			const episode = { title: `Episode ${Date.now()}` };
			const episodeId = await createEpisode(page, projectId, episode);

			// Try to generate without content
			const generateButton = page.locator('button:has-text("Generate"), button:has-text("Generate Podcast")');

			if (await generateButton.isVisible({ timeout: 2000 }).catch(() => false)) {
				await generateButton.click();

				// Should show error
				await expect(page.locator('text=/content|source|required/i')).toBeVisible({ timeout: 5000 });
			} else {
				// Generate button should be disabled
				await expect(generateButton).toBeDisabled();
			}
		});
	});
});
