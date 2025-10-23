import { Page, expect } from '@playwright/test';

/**
 * Project helper functions for E2E tests
 */

export interface ProjectData {
  title: string;
  description?: string;
}

/**
 * Create a new project
 */
export async function createProject(page: Page, project: ProjectData): Promise<string> {
  // Navigate to dashboard first
  await page.goto('/dashboard');

  // Click create project button
  await page.click('button:has-text("Create Project")');

  // Fill in project details
  await page.fill('input[placeholder*="title" i], input[placeholder*="project" i]', project.title);

  if (project.description) {
    const descField = page.locator('input[placeholder*="description" i], textarea').first();
    await descField.fill(project.description);
  }

  // Submit form
  await page.click('button:has-text("Create Project")');

  // Wait for project to appear in list
  await expect(page.locator(`text=${project.title}`)).toBeVisible({ timeout: 10000 });

  // Extract project ID from URL after clicking the project
  await page.click(`text=${project.title}`);
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
