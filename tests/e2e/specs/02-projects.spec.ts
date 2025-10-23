import { test, expect } from '@playwright/test';
import { signUpAndLogin } from '../utils/auth-helpers';
import { createProject, navigateToProject, deleteProject, verifyProjectExists } from '../utils/project-helpers';

test.describe('Project Management', () => {
	test.describe('Create Project', () => {
		test('should display create project button on dashboard', async ({ page }) => {
			await signUpAndLogin(page);
			await page.goto('/dashboard');

			// Verify create button exists
			await expect(page.locator('button:has-text("Create Project")')).toBeVisible();
		});

		test('should create project with title only', async ({ page }) => {
			await signUpAndLogin(page);

			const project = {
				title: `Test Project ${Date.now()}`,
			};

			const projectId = await createProject(page, project);

			// Should navigate to project page
			await expect(page).toHaveURL(`/projects/${projectId}`);
			await expect(page.locator(`text=${project.title}`)).toBeVisible();
		});

		test('should create project with title and description', async ({ page }) => {
			await signUpAndLogin(page);

			const project = {
				title: `Test Project ${Date.now()}`,
				description: 'This is a test project description',
			};

			const projectId = await createProject(page, project);

			// Verify project details
			await expect(page).toHaveURL(`/projects/${projectId}`);
			await expect(page.locator(`text=${project.title}`)).toBeVisible();
			await expect(page.locator(`text=${project.description}`)).toBeVisible();
		});

		test('should show validation error for empty title', async ({ page }) => {
			await signUpAndLogin(page);
			await page.goto('/dashboard');

			await page.click('button:has-text("Create Project")');

			// Try to submit with empty title
			const submitButton = page.locator('button:has-text("Create Project"), button:has-text("Create")').last();
			await submitButton.click();

			// Should show validation error or prevent submission
			const titleInput = page.locator('input[placeholder*="title" i], input[placeholder*="project" i]');
			await expect(titleInput).toHaveAttribute('required', '');
		});

		test('should create multiple projects', async ({ page }) => {
			await signUpAndLogin(page);

			const project1 = { title: `Project A ${Date.now()}` };
			const project2 = { title: `Project B ${Date.now()}` };

			await createProject(page, project1);
			await createProject(page, project2);

			// Verify both projects exist on dashboard
			await page.goto('/dashboard');
			await expect(page.locator(`text=${project1.title}`)).toBeVisible();
			await expect(page.locator(`text=${project2.title}`)).toBeVisible();
		});
	});

	test.describe('View Project', () => {
		test('should display project details', async ({ page }) => {
			await signUpAndLogin(page);

			const project = {
				title: `View Test ${Date.now()}`,
				description: 'Test description for viewing',
			};

			const projectId = await createProject(page, project);

			// Verify project page elements
			await expect(page.locator(`text=${project.title}`)).toBeVisible();
			await expect(page.locator(`text=${project.description}`)).toBeVisible();
			await expect(page.locator('button:has-text("Create Episode")')).toBeVisible();
		});

		test('should display empty state when no episodes', async ({ page }) => {
			await signUpAndLogin(page);

			const project = { title: `Empty Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			// Should show empty state message
			await expect(
				page.locator('text=/no episodes|create your first episode|get started/i')
			).toBeVisible();
		});

		test('should navigate to project from dashboard', async ({ page }) => {
			await signUpAndLogin(page);

			const project = { title: `Nav Test ${Date.now()}` };
			const projectId = await createProject(page, project);

			await page.goto('/dashboard');
			await page.click(`text=${project.title}`);

			await expect(page).toHaveURL(`/projects/${projectId}`);
		});
	});

	test.describe('Edit Project', () => {
		test('should update project title', async ({ page }) => {
			await signUpAndLogin(page);

			const project = { title: `Original Title ${Date.now()}` };
			const projectId = await createProject(page, project);

			// Find and click edit button
			const editButton = page.locator('button:has-text("Edit"), [aria-label="Edit project"]').first();
			await editButton.click();

			// Update title
			const newTitle = `Updated Title ${Date.now()}`;
			const titleInput = page.locator('input[placeholder*="title" i]');
			await titleInput.clear();
			await titleInput.fill(newTitle);

			// Save changes
			await page.click('button:has-text("Save"), button:has-text("Update")');

			// Verify updated title
			await expect(page.locator(`text=${newTitle}`)).toBeVisible({ timeout: 5000 });
		});

		test('should update project description', async ({ page }) => {
			await signUpAndLogin(page);

			const project = {
				title: `Desc Test ${Date.now()}`,
				description: 'Original description',
			};
			const projectId = await createProject(page, project);

			// Edit project
			const editButton = page.locator('button:has-text("Edit"), [aria-label="Edit project"]').first();
			await editButton.click();

			// Update description
			const newDescription = 'Updated description text';
			const descInput = page.locator('input[placeholder*="description" i], textarea').first();
			await descInput.clear();
			await descInput.fill(newDescription);

			// Save
			await page.click('button:has-text("Save"), button:has-text("Update")');

			// Verify
			await expect(page.locator(`text=${newDescription}`)).toBeVisible({ timeout: 5000 });
		});
	});

	test.describe('Delete Project', () => {
		test('should delete project', async ({ page }) => {
			await signUpAndLogin(page);

			const project = { title: `Delete Test ${Date.now()}` };
			const projectId = await createProject(page, project);

			// Delete the project
			await deleteProject(page, projectId);

			// Verify redirect to dashboard
			await expect(page).toHaveURL(/\/dashboard/);

			// Verify project no longer exists
			await expect(page.locator(`text=${project.title}`)).not.toBeVisible();
		});

		test('should show confirmation dialog before delete', async ({ page }) => {
			await signUpAndLogin(page);

			const project = { title: `Confirm Delete ${Date.now()}` };
			const projectId = await createProject(page, project);

			// Click delete button
			const deleteButton = page.locator('button:has-text("Delete"), [aria-label="Delete project"]').first();
			await deleteButton.click();

			// Should show confirmation dialog
			await expect(
				page.locator('text=/are you sure|confirm|delete this project/i')
			).toBeVisible({ timeout: 5000 });
		});

		test('should cancel delete operation', async ({ page }) => {
			await signUpAndLogin(page);

			const project = { title: `Cancel Delete ${Date.now()}` };
			const projectId = await createProject(page, project);

			// Click delete
			const deleteButton = page.locator('button:has-text("Delete"), [aria-label="Delete project"]').first();
			await deleteButton.click();

			// Click cancel in confirmation dialog
			await page.click('button:has-text("Cancel"), button:has-text("No")');

			// Should still be on project page
			await expect(page).toHaveURL(`/projects/${projectId}`);
			await expect(page.locator(`text=${project.title}`)).toBeVisible();
		});
	});

	test.describe('Project List', () => {
		test('should display all user projects on dashboard', async ({ page }) => {
			await signUpAndLogin(page);

			// Create multiple projects
			const projects = [
				{ title: `Project 1 ${Date.now()}` },
				{ title: `Project 2 ${Date.now() + 1}` },
				{ title: `Project 3 ${Date.now() + 2}` },
			];

			for (const project of projects) {
				await createProject(page, project);
			}

			// Go to dashboard and verify all projects visible
			await page.goto('/dashboard');
			for (const project of projects) {
				await expect(page.locator(`text=${project.title}`)).toBeVisible();
			}
		});

		test('should show empty state when no projects', async ({ page }) => {
			await signUpAndLogin(page);
			await page.goto('/dashboard');

			// Should show empty state
			await expect(
				page.locator('text=/no projects|create your first project|get started/i')
			).toBeVisible();
		});
	});

	test.describe('Project Access Control', () => {
		test('should not allow access to other user projects', async ({ page }) => {
			// User A creates project
			const userA = await signUpAndLogin(page);
			const project = { title: `Private Project ${Date.now()}` };
			const projectId = await createProject(page, project);

			// Logout
			await page.goto('/dashboard');
			const logoutButton = page.locator('button:has-text("Logout"), button:has-text("Sign out")').first();
			await logoutButton.click();

			// User B tries to access
			await signUpAndLogin(page);
			await page.goto(`/projects/${projectId}`);

			// Should show error or redirect
			await expect(
				page.locator('text=/not found|access denied|unauthorized|forbidden/i')
			).toBeVisible({ timeout: 5000 });
		});
	});

	test.describe('Project Navigation', () => {
		test('should navigate back to dashboard from project', async ({ page }) => {
			await signUpAndLogin(page);

			const project = { title: `Nav Back Test ${Date.now()}` };
			await createProject(page, project);

			// Find and click dashboard/back link
			const backLink = page.locator('a:has-text("Dashboard"), a:has-text("Back"), [aria-label="Back to dashboard"]').first();
			await backLink.click();

			await expect(page).toHaveURL(/\/dashboard/);
		});

		test('should show project in breadcrumb navigation', async ({ page }) => {
			await signUpAndLogin(page);

			const project = { title: `Breadcrumb Test ${Date.now()}` };
			const projectId = await createProject(page, project);

			// Check for breadcrumb with project title
			const breadcrumb = page.locator('[aria-label="Breadcrumb"], nav').first();
			await expect(breadcrumb.locator(`text=${project.title}`)).toBeVisible();
		});
	});
});
