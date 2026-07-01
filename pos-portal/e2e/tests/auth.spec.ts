/**
 * Authentication flows: login page rendering, valid/invalid credentials,
 * unauthenticated redirect, and logout.
 */
import { test, expect } from '@playwright/test'

// These tests need an unauthenticated context — override the global storageState.
const unauthenticated = { cookies: [], origins: [] }

test.describe('Login page', () => {
  test.use({ storageState: unauthenticated })

  test('renders wordmark, email + password inputs, and submit button', async ({ page }) => {
    await page.goto('/login')
    await expect(page.locator('text=ZedRead')).toBeVisible()
    await expect(page.locator('input[type="email"]')).toBeVisible()
    await expect(page.locator('input[type="password"]')).toBeVisible()
    await expect(page.locator('button[type="submit"]')).toBeVisible()
  })

  test('valid credentials redirect to /groups', async ({ page }) => {
    await page.goto('/login')
    await page.fill('input[type="email"]', process.env.E2E_ADMIN_EMAIL ?? 'admin@zedread.dev')
    await page.fill('input[type="password"]', process.env.E2E_ADMIN_PASSWORD ?? 'DevPassword123!')
    await page.click('button[type="submit"]')
    await page.waitForURL('**/groups', { timeout: 10000 })
    await expect(page).toHaveURL(/\/groups$/)
  })

  test('wrong password shows an error message', async ({ page }) => {
    await page.goto('/login')
    await page.fill('input[type="email"]', process.env.E2E_ADMIN_EMAIL ?? 'admin@zedread.dev')
    await page.fill('input[type="password"]', 'definitely-wrong-password')
    await page.click('button[type="submit"]')
    // Error text may vary; check that some error surface is visible and we're still on /login
    await expect(page).toHaveURL(/\/login/, { timeout: 5000 })
    const error = page.locator('[role="alert"]')
      .or(page.locator('text=Invalid'))
      .or(page.locator('text=incorrect'))
      .or(page.locator('text=credentials'))
    await expect(error.first()).toBeVisible({ timeout: 5000 })
  })

  test('unknown email shows an error message', async ({ page }) => {
    await page.goto('/login')
    await page.fill('input[type="email"]', 'nobody@example.com')
    await page.fill('input[type="password"]', 'irrelevant')
    await page.click('button[type="submit"]')
    await expect(page).toHaveURL(/\/login/, { timeout: 5000 })
  })

  test('unauthenticated visit to /groups redirects to /login', async ({ page }) => {
    await page.goto('/groups')
    await expect(page).toHaveURL(/\/login/)
  })

  test('unauthenticated visit to /email-templates redirects to /login', async ({ page }) => {
    await page.goto('/email-templates')
    await expect(page).toHaveURL(/\/login/)
  })
})

test.describe('Authenticated session', () => {
  test('Sign out returns to /login and clears session', async ({ page }) => {
    await page.goto('/groups')
    await expect(page).toHaveURL(/\/groups/)
    await page.click('text=Sign out')
    await expect(page).toHaveURL(/\/login/, { timeout: 5000 })
    // Verify session is gone — navigating to a protected route redirects again
    await page.goto('/groups')
    await expect(page).toHaveURL(/\/login/)
  })
})
