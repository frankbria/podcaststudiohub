import { Page, expect } from '@playwright/test';

/**
 * Episode helper functions for E2E tests
 */

export interface EpisodeData {
  title: string;
  description?: string;
}

export interface ContentSource {
  type: 'url' | 'text';
  value: string;
}

/**
 * Create a new episode within a project
 */
export async function createEpisode(page: Page, projectId: string, episode: EpisodeData): Promise<string> {
  // Navigate to project first
  await page.goto(`/projects/${projectId}`);

  // Click create episode button
  await page.click('button:has-text("Create Episode")');

  // Fill in episode details
  await page.fill('input[placeholder*="title" i], input[placeholder*="episode" i]', episode.title);

  if (episode.description) {
    const descField = page.locator('textarea, input[placeholder*="description" i]').first();
    if (await descField.isVisible({ timeout: 1000 }).catch(() => false)) {
      await descField.fill(episode.description);
    }
  }

  // Submit form
  await page.click('button:has-text("Create Episode"), button:has-text("Create")');

  // Should redirect to episode page
  await expect(page).toHaveURL(/\/episodes\/[a-f0-9-]+/);

  const episodeId = page.url().match(/\/episodes\/([a-f0-9-]+)/)?.[1];
  if (!episodeId) {
    throw new Error('Failed to extract episode ID');
  }

  return episodeId;
}

/**
 * Add content source to an episode
 */
export async function addContentSource(page: Page, episodeId: string, source: ContentSource) {
  // Navigate to episode if not already there
  if (!page.url().includes(`/episodes/${episodeId}`)) {
    await page.goto(`/episodes/${episodeId}`);
  }

  // Click add content button
  await page.click('button:has-text("Add Content")');

  // Select source type
  if (source.type === 'url') {
    // Click URL button or tab
    const urlButton = page.locator('button:has-text("URL"), [role="tab"]:has-text("URL")').first();
    if (await urlButton.isVisible({ timeout: 1000 }).catch(() => false)) {
      await urlButton.click();
    }

    // Fill URL input
    await page.fill('input[type="url"], input[placeholder*="url" i]', source.value);
  } else {
    // Click Text button or tab
    const textButton = page.locator('button:has-text("Text"), [role="tab"]:has-text("Text")').first();
    if (await textButton.isVisible({ timeout: 1000 }).catch(() => false)) {
      await textButton.click();
    }

    // Fill text area
    await page.fill('textarea, input[placeholder*="text" i]', source.value);
  }

  // Submit
  await page.click('button:has-text("Add Content"), button:has-text("Add")');

  // Wait for content to appear in list
  await page.waitForTimeout(1000); // Brief wait for UI update
}

/**
 * Generate podcast for an episode
 */
export async function generatePodcast(page: Page, episodeId: string) {
  // Navigate to episode if not already there
  if (!page.url().includes(`/episodes/${episodeId}`)) {
    await page.goto(`/episodes/${episodeId}`);
  }

  // Click generate button
  await page.click('button:has-text("Generate Podcast"), button:has-text("Generate")');

  // Verify status changes to queued
  await expect(page.locator('text=queued, text=Queued')).toBeVisible({ timeout: 10000 });
}

/**
 * Wait for podcast generation to complete
 * @param timeout Maximum time to wait in milliseconds (default: 5 minutes)
 */
export async function waitForGeneration(page: Page, episodeId: string, timeout: number = 300000) {
  // Navigate to episode if not already there
  if (!page.url().includes(`/episodes/${episodeId}`)) {
    await page.goto(`/episodes/${episodeId}`);
  }

  // Wait for complete status
  await expect(page.locator('text=complete, text=Complete')).toBeVisible({ timeout });
}

/**
 * Verify audio player is visible and functional
 */
export async function verifyAudioPlayer(page: Page) {
  // Check audio element exists
  await expect(page.locator('audio')).toBeVisible({ timeout: 5000 });

  // Check for player controls
  const playButton = page.locator('button[aria-label*="play" i]').first();
  await expect(playButton).toBeVisible();
}

/**
 * Delete content source from episode
 */
export async function deleteContentSource(page: Page, sourceIndex: number = 0) {
  const deleteButtons = page.locator('button:has-text("Delete"), button[aria-label*="delete" i]');
  const deleteButton = deleteButtons.nth(sourceIndex);

  if (await deleteButton.isVisible({ timeout: 1000 }).catch(() => false)) {
    await deleteButton.click();

    // Confirm if needed
    const confirmButton = page.locator('button:has-text("Confirm"), button:has-text("Delete")').first();
    if (await confirmButton.isVisible({ timeout: 1000 }).catch(() => false)) {
      await confirmButton.click();
    }
  }
}
