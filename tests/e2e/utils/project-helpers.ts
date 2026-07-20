import { Page, expect } from '@playwright/test';

/**
 * Project helper functions for E2E tests
 */

export interface ProjectData {
  title: string;
  description?: string;
}

/**
 * Create a new project and return its id.
 *
 * The dashboard "Create Project" trigger and the dialog submit share the same
 * label, so both selectors are scoped (trigger by role, submit inside the
 * dialog) to avoid Playwright strict-mode ambiguity.
 */
export async function createProject(page: Page, project: ProjectData): Promise<string> {
  await page.goto('/dashboard');

  // Open the create dialog (header trigger; .first() guards the empty-state CTA)
  await page.getByRole('button', { name: 'Create Project' }).first().click();

  const dialog = page.getByRole('dialog');
  await dialog.locator('#project-title').fill(project.title);
  if (project.description) {
    await dialog.locator('#project-description').fill(project.description);
  }

  // Submit (scoped to the dialog to disambiguate from the page trigger)
  await dialog.locator('button[type="submit"]').click();
  await expect(dialog).toBeHidden({ timeout: 10000 });

  // The new project appears as a card whose title is a link; navigate via it.
  const card = page.getByRole('link', { name: `Open project: ${project.title}` });
  await expect(card).toBeVisible({ timeout: 10000 });
  await card.click();

  await expect(page).toHaveURL(/\/projects\/[a-f0-9-]+/);
  const projectId = page.url().match(/\/projects\/([a-f0-9-]+)/)?.[1];
  if (!projectId) {
    throw new Error('Failed to extract project ID');
  }
  return projectId;
}

/**
 * Navigate to a specific project
 */
export async function navigateToProject(page: Page, projectId: string) {
  await page.goto(`/projects/${projectId}`);
  await expect(page).toHaveURL(`/projects/${projectId}`);
}

/**
 * Delete a project (if delete functionality exists)
 */
export async function deleteProject(page: Page, projectId: string) {
  await navigateToProject(page, projectId);

  // Look for delete button (adjust selector based on your UI)
  const deleteButton = page.locator('button:has-text("Delete"), button[aria-label*="delete" i]');

  if (await deleteButton.isVisible({ timeout: 1000 }).catch(() => false)) {
    await deleteButton.click();

    // Confirm deletion if there's a confirmation dialog
    const confirmButton = page.locator('button:has-text("Confirm"), button:has-text("Delete")');
    if (await confirmButton.isVisible({ timeout: 1000 }).catch(() => false)) {
      await confirmButton.click();
    }
  }
}

/**
 * Verify project exists in dashboard
 */
export async function verifyProjectExists(page: Page, projectTitle: string) {
  await page.goto('/dashboard');
  await expect(page.locator(`text=${projectTitle}`)).toBeVisible();
}
