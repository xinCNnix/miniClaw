/**
 * E2E Smoke Tests for miniClaw
 *
 * Tests the complete user flow from frontend to backend
 */

import { test, expect } from '@playwright/test';

// Test configuration
const FRONTEND_URL = process.env.BASE_URL || 'http://localhost:3000';
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8002';

test.describe('miniClaw Smoke Tests', () => {
  test('should load the homepage', async ({ page }) => {
    await page.goto(FRONTEND_URL);

    // Check page title
    await expect(page).toHaveTitle(/miniClaw/);

    // Check for main content area
    const main = page.locator('main');
    await expect(main).toBeVisible();
  });

  test('should navigate to chat page', async ({ page }) => {
    await page.goto(FRONTEND_URL);

    // Click on chat link if exists
    const chatLink = page.locator('a[href*="chat"]').first();
    if (await chatLink.isVisible().catch(() => false)) {
      await chatLink.click();
      await page.waitForURL('**/chat', { timeout: 5000 });
    }

    // Check main area is loaded
    const main = page.locator('main');
    await expect(main.first()).toBeVisible({ timeout: 10000 });
  });

  test('should have accessible frontend', async ({ page }) => {
    await page.goto(FRONTEND_URL);
    const title = await page.title();
    expect(title).toContain('miniClaw');
  });
});

test.describe('Chat Functionality', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/chat`);
    await page.waitForLoadState('domcontentloaded');
  });

  test('should display chat input', async ({ page }) => {
    const input = page.locator('textarea');
    await expect(input.first()).toBeVisible({ timeout: 10000 });
  });

  test('should display send button icon', async ({ page }) => {
    // Send button has Send icon from lucide-react
    const sendButton = page.locator('button svg').first();
    await expect(sendButton).toBeVisible({ timeout: 10000 });
  });

  test('should have main content area', async ({ page }) => {
    const main = page.locator('main');
    await expect(main.first()).toBeVisible({ timeout: 10000 });
  });
});

test.describe('Backend API Tests', () => {
  test.beforeAll(async () => {
    // Check if backend is running, skip tests if not
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 5000);
      const response = await fetch(`${BACKEND_URL}/health`, { signal: controller.signal });
      clearTimeout(timeoutId);
      if (!response.ok) throw new Error('Backend not healthy');
    } catch (e) {
      test.skip(true, 'Backend not available, skipping API tests');
    }
  });

  test('should access health check', async () => {
    const response = await fetch(`${BACKEND_URL}/health`);
    expect(response.ok).toBeTruthy();
    const data = await response.json();
    expect(data).toHaveProperty('status');
  });

  test('should have API docs', async () => {
    const response = await fetch(`${BACKEND_URL}/docs`);
    expect(response.ok).toBeTruthy();
  });

  test('should handle file operations API', async () => {
    const response = await fetch(`${BACKEND_URL}/api/files?path=.`);
    expect(response.ok).toBeTruthy();
    const data = await response.json();
    expect(data).toHaveProperty('files');
  });

  test('should handle sessions API', async () => {
    const response = await fetch(`${BACKEND_URL}/api/sessions`);
    expect(response.ok).toBeTruthy();
    const data = await response.json();
    expect(data).toHaveProperty('sessions');
  });
});
