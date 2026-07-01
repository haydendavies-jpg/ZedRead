/**
 * Email Templates page: list, create, edit, deactivate.
 * Accessible to admin-role portal users only.
 */
import { test, expect } from '@playwright/test'

const uid = () => `${Date.now()}-${Math.random().toString(36).slice(2, 5)}`

test.describe('Email Templates list', () => {
  test('renders page title and New Template button', async ({ page }) => {
    await page.goto('/email-templates')
    await expect(page.getByRole('heading', { name: 'Email Templates' })).toBeVisible()
    await expect(page.getByRole('button', { name: /New Template/ })).toBeVisible()
  })

  test('seeded billing_info_request template is visible and marked as system', async ({ page }) => {
    await page.goto('/email-templates')
    await expect(page.locator('text=billing_info_request')).toBeVisible()
    await expect(page.locator('text=(system)').or(page.locator('[data-system="true"]'))).toBeVisible()
  })

  test('system template has no Delete button (only Edit / Deactivate)', async ({ page }) => {
    await page.goto('/email-templates')
    const systemRow = page.locator('tr', { hasText: 'billing_info_request' })
    await expect(systemRow.locator('button:has-text("Delete")')).toHaveCount(0)
    await expect(systemRow.locator('button:has-text("Edit")')).toBeVisible()
  })
})

test.describe('Create email template', () => {
  test('creates a new template and it appears in the list', async ({ page }) => {
    const key = `e2e_template_${uid()}`
    const displayName = `E2E Template ${uid()}`
    const subject = 'Test subject for E2E'
    const body = 'Hello $entity_name, this is a $entity_type test.'

    await page.goto('/email-templates')
    await page.getByRole('button', { name: /New Template/ }).click()
    await page.waitForSelector('text=New Email Template')

    await page.locator('input[placeholder="billing_info_request"]').fill(key)
    const requiredInputs = page.locator('form input[required]')
    await requiredInputs.nth(1).fill(displayName)
    await requiredInputs.nth(2).fill(subject)
    await page.locator('form textarea').fill(body)

    await page.getByRole('button', { name: 'Create' }).click()
    await page.waitForSelector(`text=${key}`, { timeout: 10000 })
    await expect(page.locator(`text=${key}`)).toBeVisible()
    await expect(page.locator(`text=${displayName}`)).toBeVisible()
  })

  test('duplicate template key shows an error', async ({ page }) => {
    await page.goto('/email-templates')
    await page.getByRole('button', { name: /New Template/ }).click()
    await page.waitForSelector('text=New Email Template')

    // billing_info_request already exists (seeded)
    await page.locator('input[placeholder="billing_info_request"]').fill('billing_info_request')
    const requiredInputs = page.locator('form input[required]')
    await requiredInputs.nth(1).fill('Duplicate')
    await requiredInputs.nth(2).fill('Subject')
    await page.locator('form textarea').fill('Body')

    await page.getByRole('button', { name: 'Create' }).click()
    await page.waitForTimeout(1000)
    // Error state: modal stays open or an error message appears
    const hasError = await page.locator('[role="alert"]')
      .or(page.locator('text=already exists'))
      .or(page.locator('text=Failed'))
      .count()
    expect(hasError).toBeGreaterThan(0)
  })
})

test.describe('Edit email template', () => {
  let templateKey: string

  test.beforeAll(async ({ browser }) => {
    templateKey = `e2e_edit_${uid()}`
    const page = await browser.newPage()
    await page.goto('/email-templates')
    await page.getByRole('button', { name: /New Template/ }).click()
    await page.waitForSelector('text=New Email Template')
    await page.locator('input[placeholder="billing_info_request"]').fill(templateKey)
    const inputs = page.locator('form input[required]')
    await inputs.nth(1).fill('E2E Edit Template')
    await inputs.nth(2).fill('Original Subject')
    await page.locator('form textarea').fill('Original body $entity_name.')
    await page.getByRole('button', { name: 'Create' }).click()
    await page.waitForSelector(`text=${templateKey}`, { timeout: 10000 })
    await page.close()
  })

  test('Edit button opens pre-filled edit modal', async ({ page }) => {
    await page.goto('/email-templates')
    const row = page.locator('tr', { hasText: templateKey })
    await row.locator('button:has-text("Edit")').click()
    await page.waitForSelector('text=Edit Email Template')
    await expect(page.locator(`input[value="${templateKey}"]`)).toBeVisible()
    await expect(page.locator('input[value="Original Subject"]')).toBeVisible()
    await expect(page.locator('textarea')).toContainText('Original body')
  })

  test('editing subject and saving updates the list', async ({ page }) => {
    await page.goto('/email-templates')
    const row = page.locator('tr', { hasText: templateKey })
    await row.locator('button:has-text("Edit")').click()
    await page.waitForSelector('text=Edit Email Template')

    const subjectInput = page.locator('input[value="Original Subject"]')
    await subjectInput.clear()
    await subjectInput.fill('Updated Subject')
    await page.getByRole('button', { name: 'Save' }).or(page.getByRole('button', { name: 'Update' })).click()
    await page.waitForTimeout(800)

    await expect(page.locator('text=Updated Subject')).toBeVisible({ timeout: 5000 })
  })

  test('Deactivate changes template status to inactive', async ({ page }) => {
    await page.goto('/email-templates')
    const row = page.locator('tr', { hasText: templateKey })
    await row.locator('button:has-text("Deactivate")').click()
    await page.waitForTimeout(800)
    // Row should now show inactive status
    const updatedRow = page.locator('tr', { hasText: templateKey })
    await expect(updatedRow.locator('text=inactive').or(updatedRow.locator('[data-status="inactive"]'))).toBeVisible({ timeout: 5000 })
  })
})
