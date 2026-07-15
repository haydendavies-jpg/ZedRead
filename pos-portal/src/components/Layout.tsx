/** Application shell: sidebar nav + main content area. Adapts based on JWT type. */

import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth, isSuperAdmin, isMgmtUser } from '../context/AuthContext'
import { useTheme } from '../context/ThemeContext'
import { ChangePasswordModal } from '../pages/ChangePasswordPage'
import { ImpersonationBanner } from './ImpersonationBanner'

const SUPER_ADMIN_NAV = [
  { to: '/groups', label: 'Groups' },
  { to: '/brands', label: 'Brands' },
  { to: '/sites', label: 'Sites' },
  { to: '/licenses', label: 'Licenses' },
]

const SUPER_ADMIN_ONLY_NAV = [
  { to: '/superadmins', label: 'SuperAdmins' },
  { to: '/users', label: 'Users' },
  { to: '/tax-templates', label: 'Tax Templates' },
  { to: '/email-templates', label: 'Email Templates' },
]

/** Nav items shown to all management users. Tax is admin-only (see Tax Templates). */
const MGMT_NAV = [
  { to: '/management/menu-studio', label: 'Menu Studio' },
  { to: '/management/menus', label: 'Menus' },
  { to: '/management/reports', label: 'Reports' },
  { to: '/management/invoices', label: 'Invoices' },
  { to: '/management/company-profile', label: 'Company Profile' },
]

/** Nav items shown to brand/group scope management users only. */
const MGMT_BRAND_NAV = [
  { to: '/management/users', label: 'Users & Access' },
  { to: '/management/access-profiles', label: 'Permission Scopes' },
]

export function Layout() {
  const { user, logout } = useAuth()
  const { theme, toggleTheme } = useTheme()

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
      isActive
        ? 'bg-brand-50 dark:bg-brand-950/40 text-brand-800 dark:text-brand-300'
        : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-gray-100'
    }`

  const [showChangePassword, setShowChangePassword] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const mgmtUser = isMgmtUser(user) ? user : null
  const superAdmin = isSuperAdmin(user) ? user : null
  const isBrandOrGroupScope = mgmtUser && (mgmtUser.scope === 'brand' || mgmtUser.scope === 'group')

  const ROLE_LABELS: Record<string, string> = { admin: 'Admin', reseller_staff: 'Reseller' }
  const scopeLabel = mgmtUser
    ? `${mgmtUser.scope.charAt(0).toUpperCase() + mgmtUser.scope.slice(1)} scope`
    : (superAdmin?.role ? ROLE_LABELS[superAdmin.role] ?? superAdmin.role : undefined)

  const closeSidebar = () => setSidebarOpen(false)

  const sidebarContent = (
    <>
      <div className="px-4 py-5 border-b border-gray-100 dark:border-gray-800">
        <span className="font-serif font-bold text-lg text-gray-900 dark:text-gray-100">ZedRead</span>
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
          {mgmtUser ? 'Management Portal' : 'Admin Portal'}
        </p>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1">
        {superAdmin && (
          <>
            {SUPER_ADMIN_NAV.map(({ to, label }) => (
              <NavLink key={to} to={to} className={linkClass} onClick={closeSidebar}>
                {label}
              </NavLink>
            ))}
            {superAdmin.role === 'admin' && (
              <>
                <div className="pt-3 pb-1 px-3 text-xs font-medium text-gray-400 dark:text-gray-500 uppercase tracking-wide">
                  Admin
                </div>
                {SUPER_ADMIN_ONLY_NAV.map(({ to, label }) => (
                  <NavLink key={to} to={to} className={linkClass} onClick={closeSidebar}>
                    {label}
                  </NavLink>
                ))}
              </>
            )}
          </>
        )}

        {mgmtUser && (
          <>
            {MGMT_NAV.map(({ to, label }) => (
              <NavLink key={to} to={to} className={linkClass} onClick={closeSidebar}>
                {label}
              </NavLink>
            ))}
            {isBrandOrGroupScope && (
              <>
                <div className="pt-3 pb-1 px-3 text-xs font-medium text-gray-400 dark:text-gray-500 uppercase tracking-wide">
                  Users
                </div>
                {MGMT_BRAND_NAV.map(({ to, label }) => (
                  <NavLink key={to} to={to} className={linkClass} onClick={closeSidebar}>
                    {label}
                  </NavLink>
                ))}
              </>
            )}
          </>
        )}
      </nav>

      <div className="px-4 py-4 border-t border-gray-100 dark:border-gray-800">
        <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{user?.email}</p>
        <p className="text-xs text-gray-400 dark:text-gray-500 capitalize">{scopeLabel}</p>
        <div className="mt-2 flex items-center gap-3">
          <button
            onClick={() => { setShowChangePassword(true); closeSidebar() }}
            className="text-xs text-brand-600 hover:text-brand-800 dark:hover:text-brand-400 transition-colors"
          >
            Change password
          </button>
          <button
            onClick={logout}
            className="text-xs text-red-500 hover:text-red-700 transition-colors"
          >
            Sign out
          </button>
          <button
            onClick={toggleTheme}
            title="Toggle theme"
            aria-label="Toggle theme"
            className="ml-auto w-7 h-7 flex items-center justify-center rounded-md border border-gray-200 dark:border-gray-700 text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-100 text-sm"
          >
            {theme === 'dark' ? '☀' : '☾'}
          </button>
        </div>
      </div>

      {showChangePassword && (
        <ChangePasswordModal onClose={() => setShowChangePassword(false)} />
      )}
    </>
  )

  return (
    <div className="flex min-h-screen bg-[var(--zr-bg)]">
      {/* Desktop sidebar — always visible at sm+ */}
      <aside className="hidden sm:flex w-56 bg-[var(--zr-sidebar)] border-r border-[var(--zr-border)] flex-col">
        {sidebarContent}
      </aside>

      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/40 sm:hidden"
          onClick={closeSidebar}
        />
      )}
      <aside
        className={`fixed inset-y-0 left-0 z-50 w-56 bg-[var(--zr-sidebar)] border-r border-[var(--zr-border)] flex flex-col transform transition-transform duration-200 sm:hidden ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {sidebarContent}
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto bg-[var(--zr-bg)] min-w-0">
        {/* Mobile header bar with hamburger */}
        <div className="flex items-center gap-3 px-4 py-3 bg-[var(--zr-sidebar)] border-b border-[var(--zr-border)] sm:hidden">
          <button
            onClick={() => setSidebarOpen(true)}
            className="p-1 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100"
            aria-label="Open menu"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <span className="font-serif font-bold text-gray-900 dark:text-gray-100 text-base">ZedRead</span>
        </div>
        <ImpersonationBanner />
        <Outlet />
      </main>
    </div>
  )
}
