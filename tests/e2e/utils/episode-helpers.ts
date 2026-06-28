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
 * Create a new episode within a project and return its id.
 * Trigger and dialog submit share the "Create Episode" label, so the submit
 * is scoped to the dialog.
 */
export async function createEpisode(page: Page, projectId: string, episode: EpisodeData): Promise<string> {
  await page.goto(`/projects/${projectId}`);

  await page.getByRole('button', { name: 'Create Episode' }).first().click();

  const dialog = page.getByRole('dialog');
  await dialog.locator('#episode-title').fill(episode.title);

  // Submit; the app routes straight to /episodes/{id} on success.
  await dialog.locator('button[type="submit"]').click();

  await expect(page).toHaveURL(/\/episodes\/[a-f0-9-]+/, { timeout: 10000 });
  const episodeId = page.url().match(/\/episodes\/([a-f0-9-]+)/)?.[1];
  if (!episodeId) {
    throw new Error('Failed to extract episode ID');
  }
  return episodeId;
}

/**
 * Add a content source (URL or text) to an episode.
 */
export async function addContentSource(page: Page, episodeId: string, source: ContentSource) {
  if (!page.url().includes(`/episodes/${episodeId}`)) {
    await page.goto(`/episodes/${episodeId}`);
  }

  await page.getByRole('button', { name: 'Add Content' }).first().click();

  const dialog = page.getByRole('dialog');
  if (source.type === 'url') {
    await dialog.getByRole('button', { name: 'URL' }).click();
    await dialog.locator('#content-url').fill(source.value);
  } else {
    await dialog.getByRole('button', { name: 'Text' }).click();
    await dialog.locator('#content-text').fill(source.value);
  }

  await dialog.locator('button[type="submit"]').click();
  await expect(dialog).toBeHidden({ timeout: 10000 });
}

/**
 * Start podcast generation and confirm the status enters the queued state.
 * Status renders as a span with aria-label "Status: <status>".
 */
export async function generatePodcast(page: Page, episodeId: string) {
  if (!page.url().includes(`/episodes/${episodeId}`)) {
    await page.goto(`/episodes/${episodeId}`);
  }

  await page.getByRole('button', { name: 'Generate Podcast' }).click();
  await expect(page.locator('[aria-label="Status: queued"]')).toBeVisible({ timeout: 10000 });
}

/**
 * Wait for podcast generation to reach the complete status.
 * @param timeout Maximum time to wait in milliseconds (default: 5 minutes)
 */
export async function waitForGeneration(page: Page, episodeId: string, timeout: number = 300000) {
  if (!page.url().includes(`/episodes/${episodeId}`)) {
    await page.goto(`/episodes/${episodeId}`);
  }
  await expect(page.locator('[aria-label="Status: complete"]')).toBeVisible({ timeout });
}

/**
 * Verify the native audio player and download control are present.
 * (Both render only once episode.s3_url is set.)
 */
export async function verifyAudioPlayer(page: Page) {
  await expect(page.locator('audio')).toBeAttached({ timeout: 5000 });
  await expect(page.getByRole('button', { name: 'Download MP3' })).toBeVisible();
}

/**
 * Delete a content source row by index (row delete buttons share an aria-label).
 */
export async function deleteContentSource(page: Page, sourceIndex: number = 0) {
  const deleteButton = page.locator('button[aria-label="Delete content source"]').nth(sourceIndex);
  await deleteButton.click();

  // Confirm via the shared ConfirmDeleteDialog.
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('button', { name: 'Delete' }).click();
  await expect(dialog).toBeHidden({ timeout: 5000 });
}
