/**
 * Sites list and detail: CRUD, billing-email inheritance from brand,
 * address fields, currency-change confirmation, billing info request button.
 */
import { test, expect } from '@playwright/test'

const uid = () => `${Date.now()}-${Math.random().toString(36).slice(2, 5)}`

let groupName: string
let brandName: string
let brandBillingEmail: string
let siteName: string

test.beforeAll(async ({ browser }) => {
  groupName = `E2E Sites-Group ${uid()}`
  brandName = `E2E Sites-Brand ${uid()}`
  brandBillingEmail = `brand-billing-${uid()}@example.com`
  siteName = `E2E Site ${uid()}`

  const page = await browser.newPage()

  // Create group
  await page.goto('/groups')
  await page.getByRole('button', { name: /New Group/ }).click()
  await page.locator('form input[placeholder="Acme Corp"]').fill(groupName)
  await page.getByRole('button', { name: 'Create' }).click()
  await page.waitForSelector(`text=${groupName}`, { timeout: 10000 })

  // Create brand with billing email
  await page.goto('/brands')
  await page.getByRole('button', { name: /New Brand/ }).click()
  await page.waitForSelector('text=New Brand')
  await page.locator('form select').first().selectOption({ label: groupName })
  await page.locator('form input[required]').first().fill(brandName)
  await page.getByRole('button', { name: 'Create' }).click()
  await page.waitForSelector(`text=${brandName}`, { timeout: 10000 })

  // Set billing email on brand
  await page.locator(`text=${brandName}`).first().click()
  await page.waitForURL('**/brands/**', { timeout: 10000 })
  await page.waitForSelector('button:has-text("Save changes")')
  await page.locator('input[type="email"][placeholder*="billing"]').fill(brandBillingEmail)
  await page.getByRole('button', { name: 'Save changes' }).click()
  await page.waitForTimeout(800)

  // Create site under brand
  await page.goto('/sites')
  await page.getByRole('button', { name: /New Site/ }).click()
  await page.waitForSelector('text=New Site')
  await page.locator('form select').first().selectOption({ label: brandName })
  await page.locator('form input[placeholder="Sydney CBD"]').fill(siteName)
  await page.getByRole('button', { name: 'Create' }).click()
  await page.waitForSelector(`text=${siteName}`, { timeout: 10000 })

  await page.close()
})

test.describe('Sites list', () => {
  test('renders page title, search input, and New Site button', async ({ page }) => {
    await page.goto('/sites')
    await expect(page.getByRole('heading', { name: 'Sites' })).toBeVisible()
    await expect(page.locator('input[placeholder*="name"]').or(page.locator('input[placeholder*="Search"]'))).toBeVisible()
    await expect(page.getByRole('button', { name: /New Site/ })).toBeVisible()
  })

  test('created site appears in list with brand column', async ({ page }) => {
    await page.goto('/sites')
    await expect(page.locator(`text=${siteName}`)).toBeVisible()
    await expect(page.locator(`text=${brandName}`)).toBeVisible()
  })
})

test.describe('Site detail', () => {
  async function openSiteDetail(page: import('@playwright/test').Page) {
    await page.goto('/sites')
    await page.locator(`text=${siteName}`).first().click()
    await page.waitForURL('**/sites/**', { timeout: 10000 })
    await page.waitForSelector('button:has-text("Save changes")', { timeout: 10000 })
    await page.waitForTimeout(500) // allow inherited billing-email query to resolve
  }

  test('shows editable profile form with address fields', async ({ page }) => {
    await openSiteDetail(page)
    await expect(page.getByRole('button', { name: 'Save changes' })).toBeVisible()
    await expect(page.locator('input[placeholder*="Street"]').or(page.locator('label:has-text("Street")'))).toBeVisible()
    await expect(page.locator('label:has-text("State")')).toBeVisible()
    await expect(page.locator('label:has-text("Postcode")')).toBeVisible()
  })

  test('billing email inherited from brand is shown with indicator', async ({ page }) => {
    await openSiteDetail(page)
    await expect(page.locator('text=Inherited from brand')).toBeVisible()
    await expect(page.locator(`text=${brandBillingEmail}`)).toBeVisible()
  })

  test('setting site-level billing email overrides inherited value', async ({ page }) => {
    const siteEmail = `site-billing-${uid()}@example.com`
    await openSiteDetail(page)

    await page.locator('input[type="email"][placeholder*="billing"]').fill(siteEmail)
    await page.getByRole('button', { name: 'Save changes' }).click()
    await page.waitForTimeout(800)

    await page.reload()
    await page.waitForSelector('button:has-text("Save changes")', { timeout: 10000 })
    await page.waitForTimeout(500)

    // Own value is now set — inherited indicator should be gone
    await expect(page.locator('text=Inherited from brand')).not.toBeVisible()
    await expect(page.locator(`input[value="${siteEmail}"]`)).toBeVisible()

    // Clean up: clear the override so other tests see inheritance again
    await page.locator('input[type="email"][placeholder*="billing"]').clear()
    await page.getByRole('button', { name: 'Save changes' }).click()
    await page.waitForTimeout(800)
  })

  test('saving address fields persists them', async ({ page }) => {
    await openSiteDetail(page)

    const streetInput = page.locator('input[placeholder*="Street"]').or(page.locator('input[id*="street"]'))
    await streetInput.fill('123 Test Street')
    await page.locator('input[placeholder*="State"]').or(page.locator('input[id*="state"]')).fill('NSW')
    await page.locator('input[placeholder*="Postcode"]').or(page.locator('input[id*="postcode"]')).fill('2000')
    await page.getByRole('button', { name: 'Save changes' }).click()
    await page.waitForTimeout(800)

    await page.reload()
    await page.waitForSelector('button:has-text("Save changes")', { timeout: 10000 })
    await expect(page.locator('input[value="123 Test Street"]')).toBeVisible()
    await expect(page.locator('input[value="NSW"]')).toBeVisible()
    await expect(page.locator('input[value="2000"]')).toBeVisible()
  })

  test('currency change shows confirmation dialog', async ({ page }) => {
    await openSiteDetail(page)

    const dialogs: string[] = []
    page.on('dialog', async (dialog) => {
      dialogs.push(dialog.message())
      await dialog.dismiss()
    })

    await page.locator('select').nth(1).selectOption('GBP')
    await page.getByRole('button', { name: 'Save changes' }).click()

    expect(dialogs.some((m) => m.includes('Changing currency'))).toBe(true)
  })

  test('"Send billing info request" link is visible', async ({ page }) => {
    await openSiteDetail(page)
    await expect(page.locator('text=Send billing info request')).toBeVisible()
  })

  test('clicking "Send billing info request" shows a result message', async ({ page }) => {
    await openSiteDetail(page)
    await page.locator('text=Send billing info request').click()
    await page.waitForTimeout(2000)
    // Should show either a success message or an error (network-blocked in CI is acceptable)
    const result = page
      .locator('text=Billing info request sent')
      .or(page.locator('text=Failed to send'))
      .or(page.locator('text=Internal server error'))
      .or(page.locator('text=No billing email'))
    await expect(result.first()).toBeVisible({ timeout: 5000 })
  })

  test('breadcrumb links back to sites list', async ({ page }) => {
    await openSiteDetail(page)
    await page.locator('text=Sites').first().click()
    await expect(page).toHaveURL(/\/sites$/)
  })
})
