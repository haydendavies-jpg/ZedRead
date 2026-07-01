import { defineConfig } from '@playwright/test'

/**
 * Playwright E2E test config for the ZedRead admin portal.
 *
 * Requires both services running:
 *   - Backend:  uvicorn app.main:app  (port 8000)
 *   - Portal:   npm run dev           (port 5173)
 *
 * Environment variables (all optional, have dev defaults):
 *   BASE_URL           Portal URL             default: http://localhost:5173
 *   CHROMIUM_PATH      Chromium executable    default: /opt/pw-browsers/chromium
 *   E2E_ADMIN_EMAIL    SuperAdmin email       default: admin@zedread.dev
 *   E2E_ADMIN_PASSWORD SuperAdmin password    default: DevPassword123!
 */
export default defineConfig({
  testDir: './e2e/tests',
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 2 : 0,
  reporter: [['html', { open: 'never', outputFolder: 'e2e/report' }], ['line']],
  globalSetup: './e2e/global-setup.ts',
  outputDir: 'e2e/test-results',
  use: {
    baseURL: process.env.BASE_URL ?? 'http://localhost:5173',
    storageState: 'e2e/.auth/admin.json',
    headless: true,
    viewport: { width: 1280, height: 900 },
    screenshot: 'only-on-failure',
    trace: 'on-first-retry',
    executablePath: process.env.CHROMIUM_PATH ?? '/opt/pw-browsers/chromium',
  },
})
