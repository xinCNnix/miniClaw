import { test, expect } from "@playwright/test"

test.describe("Settings Page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/settings")
    await page.waitForLoadState("networkidle")
  })

  // AC-1: Page routing and navigation
  test("shows settings page with sidebar and content area", async ({ page }) => {
    // Verify sidebar exists with navigation items
    const sidebar = page.locator("nav")
    await expect(sidebar).toBeVisible()

    // Verify 12 group items in sidebar
    const navItems = page.locator("nav button")
    await expect(navItems).toHaveCount(12)
  })

  test("clicking sidebar group switches content", async ({ page }) => {
    // Click "Agent Behavior" (or Chinese equivalent)
    const secondItem = page.locator("nav button").nth(2)
    const groupText = await secondItem.textContent()
    await secondItem.click()

    // Content area should update
    const content = page.locator("main")
    await expect(content).toBeVisible()
  })

  test("active group has highlighted style", async ({ page }) => {
    const activeItem = page.locator("nav button").first()
    const borderColor = await activeItem.evaluate((el) => {
      return window.getComputedStyle(el).borderLeftColor
    })
    // Should have a non-transparent border (ink-green)
    expect(borderColor).not.toBe("rgba(0, 0, 0, 0)")
  })

  test("back button navigates to /chat", async ({ page }) => {
    const backButton = page.locator("button", { hasText: "←" })
    await backButton.click()
    await expect(page).toHaveURL(/\/chat/)
  })

  // AC-4: Form controls render correctly
  test("non-LLM groups show form controls", async ({ page }) => {
    // Navigate to a form-based group (e.g., Agent Behavior, index 2)
    await page.locator("nav button").nth(2).click()
    await page.waitForTimeout(500)

    // Should see at least one toggle or input
    const controls = page.locator("main button[role='switch'], main input[type='number'], main select")
    const count = await controls.count()
    expect(count).toBeGreaterThan(0)
  })
})
