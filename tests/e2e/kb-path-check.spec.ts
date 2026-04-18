/**
 * E2E Test: Check Knowledge Base Path
 *
 * This test reproduces the user scenario: "请检查下知识库路径"
 * Tests the complete flow from frontend chat to backend agent response.
 */

import { test, expect } from '@playwright/test';

// Test configuration
const FRONTEND_URL = process.env.BASE_URL || 'http://localhost:3000';
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8002';

test.describe('Knowledge Base Path Check - E2E', () => {
  test.beforeAll(async () => {
    // Verify backend is running
    try {
      const response = await fetch(`${BACKEND_URL}/health`);
      expect(response.ok).toBeTruthy();
    } catch (error) {
      throw new Error(`Backend not running at ${BACKEND_URL}`);
    }
  });

  test('should handle "check knowledge base path" request', async ({ page }) => {
    // Navigate to chat page
    await page.goto(`${FRONTEND_URL}/chat`);
    await page.waitForLoadState('networkidle');

    // Find chat input
    const chatInput = page.locator('textarea, [data-testid="chat-input"], #chat-input').first();
    await expect(chatInput).toBeVisible({ timeout: 10000 });

    // Send message: "请检查下知识库路径"
    await chatInput.fill('请检查下知识库路径');

    // Find and click send button
    const sendButton = page.locator('button:has-text("Send"), button:has-text("发送"), [data-testid="send-button"]').first();
    await sendButton.click();

    // Wait for agent response (at least one message)
    const messages = page.locator('[data-testid="message"], .message, [class*="message"]');
    await expect(messages.nth(1)).toBeVisible({ timeout: 30000 });

    // Capture agent's response
    const agentResponse = await messages.nth(1).textContent();
    console.log('Agent Response:', agentResponse);

    // Verify agent responded
    expect(agentResponse).not.toBeNull();
    expect(agentResponse?.length).toBeGreaterThan(0);

    // Check if response mentions knowledge base
    const responseText = agentResponse?.toLowerCase() || '';
    const mentionsKB = responseText.includes('knowledge') ||
                       responseText.includes('base') ||
                       responseText.includes('路径') ||
                       responseText.includes('directory');

    console.log('Mentions Knowledge Base:', mentionsKB);

    // Take screenshot for debugging
    await page.screenshot({ path: 'test-results/kb-path-check.png', fullPage: true });
  });

  test('should check knowledge base API directly', async () => {
    // Check KB stats API
    const statsResponse = await fetch(`${BACKEND_URL}/api/kb/stats`);
    expect(statsResponse.ok).toBeTruthy();

    const statsData = await statsResponse.json();
    console.log('KB Stats:', statsData);

    // Check if KB directory exists and has documents
    expect(statsData).toHaveProperty('total_documents');
    expect(statsData).toHaveProperty('total_chunks');

    console.log('Total Documents:', statsData.total_documents);
    console.log('Total Chunks:', statsData.total_chunks);

    // Verify KB is accessible
    if (statsData.total_documents === 0) {
      console.warn('WARNING: Knowledge base is empty!');
    }
  });

  test('should test search_kb API', async () => {
    // Test search endpoint
    const searchResponse = await fetch(`${BACKEND_URL}/api/kb/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: 'test', top_k: 3 }),
    });

    expect(searchResponse.ok).toBeTruthy();

    const searchData = await searchResponse.json();
    console.log('Search Results:', searchData);

    // Check response format
    expect(searchData).toHaveProperty('results');
    expect(Array.isArray(searchData.results)).toBeTruthy();

    console.log('Number of Results:', searchData.results.length);

    // If no results, this indicates the embedding model issue
    if (searchData.results.length === 0) {
      console.warn('WARNING: Search returned no results!');
      console.warn('This indicates embedding model is not loaded properly');
    }
  });
});

test.describe('Knowledge Base Error Analysis', () => {
  test('should diagnose embedding model status', async () => {
    // Check if embedding model is ready by testing search
    const searchResponse = await fetch(`${BACKEND_URL}/api/kb/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: 'test', top_k: 1 }),
    });

    if (searchResponse.ok) {
      const searchData = await searchResponse.json();

      if (searchData.results && searchData.results.length === 0) {
        console.error('ERROR: Knowledge base search returns empty results');
        console.error('Root cause: Embedding model not initialized');
        console.error('File to check: backend/app/core/rag_engine.py:451-453');
      } else {
        console.log('OK: Knowledge base search is working');
      }
    } else {
      console.error('ERROR: Search endpoint not accessible');
    }
  });

  test('should verify KB directory structure', async () => {
    // List files in KB directory
    const filesResponse = await fetch(`${BACKEND_URL}/api/files?path=data/knowledge_base`);

    if (filesResponse.ok) {
      const filesData = await filesResponse.json();
      console.log('KB Directory Files:', filesData.files?.length || 0);

      if (filesData.files && filesData.files.length > 0) {
        console.log('Sample files:', filesData.files.slice(0, 5));
      } else {
        console.warn('WARNING: KB directory is empty');
      }
    }
  });
});
