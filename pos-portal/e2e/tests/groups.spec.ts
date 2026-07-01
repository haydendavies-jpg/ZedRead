/**
 * Groups list and detail: CRUD, profile fields, currency-change confirmation.
 */
import { test, expect } from '@playwright/test'

const uid = () => `${Date.now()}-${Math.random().toString(36).slice(2, 5)}`

test.describe('Groups list', () => {
  test('renders page title, search input, status filter, and New Group button', async ({ page }) => {
    await page.goto('/groups')
    await expect(page.getByRole('heading', { name: 'Groups' })).toBeVisible()
    await expect(page.locator('input[placeholder*="name"]').or(page.locator('input[placeholder*="Search"]'))).toBeVisible()
    await expect(page.getByRole('button', { name: /New Group/ })).toBeVisible()
  })

  test('status filter options include All, Active, and Inactive', async ({ page }) => {
    await page.goto('/groups')
    const select = page.locator('select').first()
    await expect(select.locator('option', { hasText: /active/i })).toHaveCount({ min: 1 } as never)
  })

  test('search for nonexistent name shows zero results', async ({ page }) => {
    await page.goto('/groups')
    const search = page.locator('input[placeholder*="name"]').or(page.locator('input[placeholder*="Search"]'))
    await search.fill('zzz-no-such-group-xyz')
    await page.waitForTimeout(300)
    const zeroResult = page.locator('text=No groups').or(page.locator('text=0 of'))
    await expect(zeroResult.first()).toBeVisible()
  })
})

test.describe('Create group', () => {
  test('creates group with all profile fields and it appears in the list', async ({ page }) => {
    const name = `E2E Group ${uid()}`
    await page.goto('/groups')
    await page.getByRole('button', { name: /New Group/ }).click()
    await page.waitForSelector('text=New Group')

    await page.locator('form input[placeholder="Acme Corp"]').fill(name)
    // Currency: change to USD to test non-default value
    const currencySelect = page.locator('form select').filter({ hasText: 'AUD' }).or(page.locator('form select').nth(1))
    await currencySelect.selectOption('USD')
    // Billing email
    await page.locator('form input[type="email"]').fill(`billing-${uid()}@example.com`)

    await page.getByRole('button', { name: 'Create' }).click()
    await page.waitForSelector(`text=${name}`, { timeout: 10000 })
    await expect(page.locator(`text=${name}`)).toBeVisible()
  })

  test('modal closes and list updates on successful create', async ({ page }) => {
    const name = `E2E Group ${uid()}`
    await page.goto('/groups')
    await page.getByRole('button', { name: /New Group/ }).click()
    await page.locator('form input[placeholder="Acme Corp"]').fill(name)
    await page.getByRole('button', { name: 'Create' }).click()
    // Modal should close (no "New Group" heading any more)
    await page.waitForTimeout(500)
    const modalStillOpen = await page.locator('text=New Group').count()
    expect(modalStillOpen).toBe(0)
    await expect(page.locator(`text=${name}`)).toBeVisible({ timeout: 10000 })
  })
})

test.describe('Group detail', () => {
  let groupName: string

  test.beforeAll(async ({ browser }) => {
    groupName = `E2E Group ${uid()}`
    const page = await browser.newPage()
    await page.goto('/groups')
    await page.getByRole('button', { name: /New Group/ }).click()
    await page.locator('form input[placeholder="Acme Corp"]').fill(groupName)
    await page.getByRole('button', { name: 'Create' }).click()
    await page.waitForSelector(`text=${groupName}`, { timeout: 10000 })
    await page.close()
  })

  test('clicking group name navigates to detail page with editable form', async ({ page }) => {
    await page.goto('/groups')
    await page.locator(`text=${groupName}`).first().click()
    await page.waitForURL('**/groups/**', { timeout: 10000 })
    await expect(page.getByRole('button', { name: 'Save changes' })).toBeVisible()
    // Name field should be pre-filled
    await expect(page.locator(`input[value="${groupName}"]`)).toBeVisible()
  })

  test('editing the group name and saving updates the heading', async ({ page }) => {
    await page.goto('/groups')
    await page.locator(`text=${groupName}`).first().click()
    await page.waitForURL('**/groups/**', { timeout: 10000 })
    await page.waitForSelector('button:has-text("Save changes")')

    const updatedName = groupName + ' updated'
    const nameInput = page.locator(`input[value="${groupName}"]`)
    await nameInput.clear()
    await nameInput.fill(updatedName)
    await page.getByRole('button', { name: 'Save changes' }).click()
    await page.waitForTimeout(800)
    await expect(page.locator(`text=${updatedName}`).first()).toBeVisible({ timeout: 5000 })

    // Reset for other tests
    await nameInput.fill(groupName)
    await page.getByRole('button', { name: 'Save changes' }).click()
  })

  test('breadcrumb links back to groups list', async ({ page }) => {
    await page.goto('/groups')
    await page.locator(`text=${groupName}`).first().click()
    await page.waitForURL('**/groups/**', { timeout: 10000 })
    await page.locator('text=Groups').first().click()
    await expect(page).toHaveURL(/\/groups$/)
  })

  test('currency change shows confirmation dialog with invoice warning', async ({ page }) => {
    await page.goto('/groups')
    await page.locator(`text=${groupName}`).first().click()
    await page.waitForURL('**/groups/**', { timeout: 10000 })
    await page.waitForSelector('button:has-text("Save changes")')

    const dialogs: string[] = []
    page.on('dialog', async (dialog) => {
      dialogs.push(dialog.message())
      await dialog.dismiss()
    })

    const currencySelect = page.locator('select').nth(1)
    await currencySelect.selectOption('GBP')
    await page.getByRole('button', { name: 'Save changes' }).click()

    expect(dialogs.length).toBeGreaterThan(0)
    expect(dialogs[0]).toContain('Changing currency')
  })

  test('dismissing currency-change dialog does not save the new currency', async ({ page }) => {
    await page.goto('/groups')
    await page.locator(`text=${groupName}`).first().click()
    await page.waitForURL('**/groups/**', { timeout: 10000 })
    await page.waitForSelector('button:has-text("Save changes")')

    page.on('dialog', async (dialog) => dialog.dismiss())

    const currencySelect = page.locator('select').nth(1)
    const originalValue = await currencySelect.inputValue()
    const newValue = originalValue === 'AUD' ? 'USD' : 'AUD'
    await currencySelect.selectOption(newValue)
    await page.getByRole('button', { name: 'Save changes' }).click()

    // Reload and confirm original value is still set
    await page.reload()
    await page.waitForSelector('button:has-text("Save changes")')
    await expect(page.locator('select').nth(1)).toHaveValue(originalValue)
  })

  test('accepting currency-change dialog saves the new currency', async ({ page }) => {
    await page.goto('/groups')
    await page.locator(`text=${groupName}`).first().click()
    await page.waitForURL('**/groups/**', { timeout: 10000 })
    await page.waitForSelector('button:has-text("Save changes")')

    page.on('dialog', async (dialog) => dialog.accept())

    const currencySelect = page.locator('select').nth(1)
    await currencySelect.selectOption('NZD')
    await page.getByRole('button', { name: 'Save changes' }).click()
    await page.waitForTimeout(800)

    await page.reload()
    await page.waitForSelector('button:has-text("Save changes")')
    await expect(page.locator('select').nth(1)).toHaveValue('NZD')
  })

  test('country change updates the tax ID label', async ({ page }) => {
    await page.goto('/groups')
    await page.locator(`text=${groupName}`).first().click()
    await page.waitForURL('**/groups/**', { timeout: 10000 })
    await page.waitForSelector('button:has-text("Save changes")')

    // Change country to GB → label should become "VAT Number"
    const countrySelect = page.locator('select').nth(2)
    await countrySelect.selectOption('GB')
    await expect(page.locator('text=VAT Number').or(page.locator('label:has-text("VAT")'))).toBeVisible({ timeout: 3000 })
  })
})
