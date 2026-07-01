/**
 * Global setup: logs in once as SuperAdmin and saves auth state so all test
 * files can reuse the session without repeating the login flow.
 */
import { chromium, type FullConfig } from '@playwright/test'
import fs from 'fs'
import path from 'path'

const AUTH_FILE = path.join(__dirname, '.auth', 'admin.json')

async function globalSetup(config: FullConfig) {
  const baseURL = config.use?.baseURL ?? 'http://localhost:5173'
  const executablePath =
    (config.use as Record<string, unknown>)?.executablePath as string | undefined
    ?? '/opt/pw-browsers/chromium'

  fs.mkdirSync(path.dirname(AUTH_FILE), { recursive: true })

  const browser = await chromium.launch({ executablePath, headless: true })
  const page = await browser.newPage()

  await page.goto(`${baseURL}/login`)
  await page.fill('input[type="email"]', process.env.E2E_ADMIN_EMAIL ?? 'admin@zedread.dev')
  await page.fill('input[type="password"]', process.env.E2E_ADMIN_PASSWORD ?? 'DevPassword123!')
  await page.click('button[type="submit"]')
  await page.waitForURL('**/groups', { timeout: 15000 })

  await page.context().storageState({ path: AUTH_FILE })
  await browser.close()
}

export default globalSetup
