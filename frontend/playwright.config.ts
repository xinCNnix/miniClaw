import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  // Tests are in frontend/e2e directory
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    actionTimeout: 60000,
    // Use system Chrome instead of downloading Playwright's
    channel: 'chrome', // Use installed Chrome/Chromium
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        channel: 'chrome', // Use system Chrome
      },
    },
  ],
  webServer: {
    command: 'echo "Servers should be running"',
    url: 'http://localhost:3000',
    reuseExistingServer: true,
  },
  timeout: 60000 * 2,
})
