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
  test.beforeAll(async () => {
    // Verify backend is running
    const response = await fetch(`${BACKEND_URL}/health`);
    expect(response.ok).toBeTruthy();
  });

  test('should load the homepage', async ({ page }) => {
    await page.goto(FRONTEND_URL);

    // Check page title
    await expect(page).toHaveTitle(/miniClaw/);

    // Check main navigation is visible
    const nav = page.locator('nav');
    await expect(nav).toBeVisible();

    // Check for main content area
    const main = page.locator('main');
    await expect(main).toBeVisible();
  });

  test('should navigate to chat page', async ({ page }) => {
    await page.goto(FRONTEND_URL);

    // Click on chat link
    await page.click('text=Chat');

    // Wait for navigation
    await page.waitForURL('**/chat');

    // Check chat interface is loaded
    const chatArea = page.locator('[data-testid="chat-area"], .chat-area, #chat-container');
    await expect(chatArea.first()).toBeVisible({ timeout: 10000 });
  });

  test('should display backend health check', async ({ page }) => {
    const response = await fetch(`${BACKEND_URL}/health`);
    const data = await response.json();

    expect(data).toHaveProperty('status', 'healthy');
  });

  test('should have accessible API docs', async ({ page }) => {
    const response = await fetch(`${BACKEND_URL}/docs`);
    expect(response.ok).toBeTruthy();
    expect(response.headers.get('content-type')).toContain('text/html');
  });

  test('should handle API error gracefully', async ({ page }) => {
    // Try to access a non-existent endpoint
    const response = await fetch(`${BACKEND_URL}/api/nonexistent`, {
      method: 'POST',
      body: JSON.stringify({ test: 'data' }),
      headers: { 'Content-Type': 'application/json' },
    });

    // Should get a 404 or 422 error, not a 500
    expect([404, 422, 405]).toContain(response.status);
  });
});

test.describe('Chat Functionality', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/chat`);
    await page.waitForLoadState('networkidle');
  });

  test('should display chat input', async ({ page }) => {
    const input = page.locator('textarea[placeholder*="message" i], textarea[placeholder*="输入" i], #chat-input, [data-testid="chat-input"]');
    await expect(input.first()).toBeVisible({ timeout: 10000 });
  });

  test('should display send button', async ({ page }) => {
    const sendButton = page.locator('button:has-text("Send"), button:has-text("发送"), [data-testid="send-button"]');
    await expect(sendButton.first()).toBeVisible({ timeout: 10000 });
  });

  test('should have file browser panel', async ({ page }) => {
    const filePanel = page.locator('[data-testid="file-browser"], .file-browser, #file-panel');
    await expect(filePanel.first()).toBeVisible({ timeout: 10000 });
  });
});

test.describe('Knowledge Base', () => {
  test('should access knowledge base API', async () => {
    const response = await fetch(`${BACKEND_URL}/api/kb/stats`);
    expect(response.ok).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('total_documents');
    expect(data).toHaveProperty('total_chunks');
  });
});

test.describe('File Operations', () => {
  test('should list files via API', async () => {
    const response = await fetch(`${BACKEND_URL}/api/files?path=.`);
    expect(response.ok).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('files');
    expect(Array.isArray(data.files)).toBeTruthy();
  });

  test('should handle invalid file path', async () => {
    const response = await fetch(`${BACKEND_URL}/api/files/read?path=/nonexistent/file.txt`);
    expect(response.status).toBeGreaterThanOrEqual(400);
  });
});

test.describe('Session Management', () => {
  test('should list sessions', async () => {
    const response = await fetch(`${BACKEND_URL}/api/sessions`);
    expect(response.ok).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('sessions');
    expect(Array.isArray(data.sessions)).toBeTruthy();
  });
});
