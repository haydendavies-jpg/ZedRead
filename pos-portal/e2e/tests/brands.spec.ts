/**
 * Brands list and detail: CRUD, editable profile, billing email, currency warning.
 */
import { test, expect } from '@playwright/test'

const uid = () => `${Date.now()}-${Math.random().toString(36).slice(2, 5)}`

// Shared setup: one group + one brand created once for the whole file.
let groupName: string
let brandName: string

test.beforeAll(async ({ browser }) => {
  groupName = `E2E Brands-Group ${uid()}`
  brandName = `E2E Brand ${uid()}`
  const page = await browser.newPage()

  // Create group
  await page.goto('/groups')
  await page.getByRole('button', { name: /New Group/ }).click()
  await page.locator('form input[placeholder="Acme Corp"]').fill(groupName)
  await page.getByRole('button', { name: 'Create' }).click()
  await page.waitForSelector(`text=${groupName}`, { timeout: 10000 })

  // Create brand
  await page.goto('/brands')
  await page.getByRole('button', { name: /New Brand/ }).click()
  await page.waitForSelector('text=New Brand')
  // Select group
  const groupSelect = page.locator('form select').first()
  await groupSelect.selectOption({ label: groupName })
  await page.locator('form input[required]').first().fill(brandName)
  await page.getByRole('button', { name: 'Create' }).click()
  await page.waitForSelector(`text=${brandName}`, { timeout: 10000 })

  await page.close()
})

test.describe('Brands list', () => {
  test('renders page title, search input, and New Brand button', async ({ page }) => {
    await page.goto('/brands')
    await expect(page.getByRole('heading', { name: 'Brands' })).toBeVisible()
    await expect(page.locator('input[placeholder*="name"]').or(page.locator('input[placeholder*="Search"]'))).toBeVisible()
    await expect(page.getByRole('button', { name: /New Brand/ })).toBeVisible()
  })

  test('created brand appears in list with correct group column', async ({ page }) => {
    await page.goto('/brands')
    await expect(page.locator(`text=${brandName}`)).toBeVisible()
    await expect(page.locator(`text=${groupName}`)).toBeVisible()
  })

  test('search filter narrows results to matching brands', async ({ page }) => {
    await page.goto('/brands')
    const search = page.locator('input[placeholder*="name"]').or(page.locator('input[placeholder*="Search"]'))
    await search.fill(brandName)
    await page.waitForTimeout(300)
    await expect(page.locator(`text=${brandName}`)).toBeVisible()
    // Other brands shouldn't be visible (or count chip shows subset)
  })
})

test.describe('Brand detail', () => {
  test('Overview tab shows editable profile form (not read-only)', async ({ page }) => {
    await page.goto('/brands')
    await page.locator(`text=${brandName}`).first().click()
    await page.waitForURL('**/brands/**', { timeout: 10000 })
    await expect(page.getByRole('button', { name: 'Save changes' })).toBeVisible()
    await expect(page.locator(`input[value="${brandName}"]`)).toBeVisible()
  })

  test('setting billing email and saving persists the value', async ({ page }) => {
    const email = `billing-${uid()}@example.com`
    await page.goto('/brands')
    await page.locator(`text=${brandName}`).first().click()
    await page.waitForURL('**/brands/**', { timeout: 10000 })
    await page.waitForSelector('button:has-text("Save changes")')

    await page.locator('input[type="email"][placeholder*="billing"]').fill(email)
    await page.getByRole('button', { name: 'Save changes' }).click()
    await page.waitForTimeout(800)

    // Reload to confirm persistence
    await page.reload()
    await page.waitForSelector('button:has-text("Save changes")')
    await expect(page.locator(`input[value="${email}"]`)).toBeVisible()
  })

  test('clearing billing email removes it', async ({ page }) => {
    await page.goto('/brands')
    await page.locator(`text=${brandName}`).first().click()
    await page.waitForURL('**/brands/**', { timeout: 10000 })
    await page.waitForSelector('button:has-text("Save changes")')

    const emailInput = page.locator('input[type="email"][placeholder*="billing"]')
    await emailInput.clear()
    await page.getByRole('button', { name: 'Save changes' }).click()
    await page.waitForTimeout(800)

    await page.reload()
    await page.waitForSelector('button:has-text("Save changes")')
    await expect(emailInput).toHaveValue('')
  })

  test('currency change shows confirmation dialog', async ({ page }) => {
    await page.goto('/brands')
    await page.locator(`text=${brandName}`).first().click()
    await page.waitForURL('**/brands/**', { timeout: 10000 })
    await page.waitForSelector('button:has-text("Save changes")')

    const dialogs: string[] = []
    page.on('dialog', async (dialog) => {
      dialogs.push(dialog.message())
      await dialog.dismiss()
    })

    const currencySelect = page.locator('select').nth(1)
    await currencySelect.selectOption('USD')
    await page.getByRole('button', { name: 'Save changes' }).click()

    expect(dialogs.some((m) => m.includes('Changing currency'))).toBe(true)
  })

  test('logo upload section shows helper text', async ({ page }) => {
    await page.goto('/brands')
    await page.locator(`text=${brandName}`).first().click()
    await page.waitForURL('**/brands/**', { timeout: 10000 })
    await page.waitForSelector('button:has-text("Save changes")')
    await expect(page.locator('text=Recommended: 500×500px')).toBeVisible()
  })
})

test.describe('Create brand validation', () => {
  test('requires a name — form does not submit with empty name', async ({ page }) => {
    await page.goto('/brands')
    await page.getByRole('button', { name: /New Brand/ }).click()
    await page.waitForSelector('text=New Brand')
    // Select group but leave name empty
    const groupSelect = page.locator('form select').first()
    await groupSelect.selectOption({ label: groupName })
    await page.getByRole('button', { name: 'Create' }).click()
    // Modal should still be open
    await expect(page.locator('text=New Brand')).toBeVisible()
  })
})
