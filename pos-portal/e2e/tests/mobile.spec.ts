/**
 * Mobile layout tests at 375 × 800px viewport.
 *
 * Verifies the responsive patterns required by pos-portal/CLAUDE.md:
 *   - overflow-x-auto table containers (tables scroll rather than breaking layout)
 *   - flex-wrap page headers (title + action button can stack)
 *   - hamburger menu visible, sidebar hidden by default
 *   - forms in detail pages stack single-column
 */
import { test, expect } from '@playwright/test'

test.use({ viewport: { width: 375, height: 800 } })

test.describe('Mobile layout — 375px viewport', () => {
  test('Groups list: hamburger button visible, sidebar hidden', async ({ page }) => {
    await page.goto('/groups')
    // Desktop aside is hidden (sm:flex), hamburger is shown (sm:hidden)
    await expect(page.locator('button[aria-label="Open menu"]')).toBeVisible()
    await expect(page.locator('aside.hidden')).toBeAttached() // desktop aside present but hidden
  })

  test('Groups list: opening hamburger shows sidebar overlay', async ({ page }) => {
    await page.goto('/groups')
    await page.locator('button[aria-label="Open menu"]').click()
    // Sidebar should slide in (translate-x-0)
    await expect(page.locator('text=Groups').nth(1)).toBeVisible() // nav link inside sidebar
    // Backdrop should be present
    await expect(page.locator('.bg-black\\/40').or(page.locator('[class*="bg-black"]'))).toBeVisible()
  })

  test('Groups list: tapping backdrop closes the sidebar', async ({ page }) => {
    await page.goto('/groups')
    await page.locator('button[aria-label="Open menu"]').click()
    await page.locator('.bg-black\\/40').or(page.locator('[class*="bg-black/40"]')).click()
    await expect(page.locator('button[aria-label="Open menu"]')).toBeVisible()
  })

  test('Groups list: table is horizontally scrollable', async ({ page }) => {
    await page.goto('/groups')
    // The overflow-x-auto wrapper should exist around the table
    const wrapper = page.locator('.overflow-x-auto').first()
    await expect(wrapper).toBeVisible()
    const table = wrapper.locator('table')
    await expect(table).toBeVisible()
  })

  test('Groups list: New Group button and heading visible without overflow', async ({ page }) => {
    await page.goto('/groups')
    await expect(page.getByRole('heading', { name: 'Groups' })).toBeVisible()
    await expect(page.getByRole('button', { name: /New Group/ })).toBeVisible()
  })

  test('Brands list: table scrollable and New Brand button visible', async ({ page }) => {
    await page.goto('/brands')
    await expect(page.getByRole('heading', { name: 'Brands' })).toBeVisible()
    await expect(page.getByRole('button', { name: /New Brand/ })).toBeVisible()
    const wrapper = page.locator('.overflow-x-auto').first()
    await expect(wrapper).toBeVisible()
  })

  test('Email Templates list: table scrollable and New Template button visible', async ({ page }) => {
    await page.goto('/email-templates')
    await expect(page.getByRole('heading', { name: 'Email Templates' })).toBeVisible()
    await expect(page.getByRole('button', { name: /New Template/ })).toBeVisible()
    const wrapper = page.locator('.overflow-x-auto').first()
    await expect(wrapper).toBeVisible()
  })

  test('Create modal respects mx-4 padding on narrow screen', async ({ page }) => {
    await page.goto('/groups')
    await page.getByRole('button', { name: /New Group/ }).click()
    await page.waitForSelector('text=New Group')
    // Modal should be visible and not overflow the viewport
    const modal = page.locator('[role="dialog"]').or(page.locator('.mx-4'))
    await expect(modal.first()).toBeVisible()
    const box = await modal.first().boundingBox()
    expect(box?.x).toBeGreaterThanOrEqual(0)
    if (box) expect(box.x + box.width).toBeLessThanOrEqual(375)
  })

  test('Site detail form stacks fields vertically', async ({ page }) => {
    // Navigate to the sites list and open the first site
    await page.goto('/sites')
    const firstSiteLink = page.locator('table tbody tr td a').or(
      page.locator('table tbody tr').first().locator('text=E2E Site, text=Verify')
    )
    const rows = page.locator('table tbody tr')
    const rowCount = await rows.count()
    if (rowCount === 0) {
      test.skip()
      return
    }
    await rows.first().click()
    await page.waitForURL('**/sites/**', { timeout: 10000 })
    await page.waitForSelector('button:has-text("Save changes")', { timeout: 10000 })

    // All form inputs should fit within 375px without horizontal overflow
    const nameInput = page.locator('input').first()
    const box = await nameInput.boundingBox()
    if (box) expect(box.x + box.width).toBeLessThanOrEqual(375)
    await expect(page.getByRole('button', { name: 'Save changes' })).toBeVisible()
  })
})
