/**
 * Shared full-screen shell for the standalone, unauthenticated pages — login,
 * forgot-password, reset-password. These don't render inside Layout.tsx (no
 * sidebar, no theme toggle), and each used to hard-code its own
 * `bg-gray-50 dark:bg-gray-900` canvas — a plain Tailwind grey that drifted
 * from `--zr-bg`, the warm cream/near-black token every authenticated page
 * sits on via Layout.tsx's <main>. The wordmark also had no dark-mode colour
 * at all, so it read as dark-on-dark against the card in dark mode. This
 * consolidates all three pages onto one shell so they can't drift again, and
 * gives each a theme toggle of its own.
 */

import type { ReactNode } from 'react'
import { useTheme } from '../context/ThemeContext'

interface AuthPageShellProps {
  /** Shown under the wordmark, e.g. "Sign in to Portal". Omit to skip the wordmark block entirely (the grant/identity selector views render their own heading instead). */
  subtitle?: string
  children: ReactNode
}

export function AuthPageShell({ subtitle, children }: AuthPageShellProps) {
  const { theme, toggleTheme } = useTheme()

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--zr-bg)] p-4 sm:p-6">
      <div className="w-full max-w-sm">
        <div className="relative bg-white dark:bg-gray-800 rounded-2xl shadow-sm border border-gray-200 dark:border-gray-700 p-8">
          <button
            type="button"
            onClick={toggleTheme}
            title="Toggle theme"
            aria-label="Toggle theme"
            className="absolute top-4 right-4 w-7 h-7 flex items-center justify-center rounded-md border border-gray-200 dark:border-gray-600 text-gray-400 dark:text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 text-sm"
          >
            {theme === 'dark' ? '☀' : '☾'}
          </button>

          {subtitle && (
            <div className="mb-6 text-center">
              <h1 className="mb-0.5 text-[var(--zr-accent-text)]" style={{ fontFamily: "'Lora', serif", fontSize: '2rem', fontWeight: 700 }}>
                ZedRead
              </h1>
              <p className="text-gray-400 dark:text-gray-500 tracking-widest uppercase" style={{ fontSize: '0.6rem' }}>
                POS You Can Count On
              </p>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-4">{subtitle}</p>
            </div>
          )}

          {children}
        </div>
      </div>
    </div>
  )
}
