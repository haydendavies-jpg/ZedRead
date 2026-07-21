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
  { to: '/pos-devices', label: 'POS Devices' },
]

const SUPER_ADMIN_ONLY_NAV = [
  { to: '/users', label: 'Users' },
  { to: '/tax-templates', label: 'Tax Templates' },
  { to: '/email-templates', label: 'Email Templates' },
]

/** Nav items shown to all management users. Tax is admin-only (see Tax Templates). */
const MGMT_NAV = [
  { to: '/management/menu-studio', label: 'Menu Studio' },
  { to: '/management/reports', label: 'Reports' },
  { to: '/management/invoices', label: 'Invoices' },
  { to: '/management/register-sessions', label: 'Register Sessions' },
  { to: '/management/devices', label: 'Devices' },
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

  // The sidebar surface (--zr-sidebar) is now a solid accent colour in BOTH
  // themes (light: #554C44, dark: #332e29), not a light/dark-toggling
  // parchment/ink pair — so its own text/hover/active styling is always
  // "light on dark" and does not follow the app-wide `dark:` variant.
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
      isActive
        ? 'bg-white/15 text-white'
        : 'text-white/70 hover:bg-white/10 hover:text-white'
    }`

  const [showChangePassword, setShowChangePassword] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const mgmtUser = isMgmtUser(user) ? user : null
  const superAdmin = isSuperAdmin(user) ? user : null
  const isBrandOrGroupScope = mgmtUser && (mgmtUser.scope === 'brand' || mgmtUser.scope === 'group')

  const ROLE_LABELS: Record<string, string> = { admin: 'Admin', reseller_staff: 'Reseller' }
  const scopeLabel = mgmtUser
    ? `${mgmtUser.scope.charAt(0).toUpperCase() + mgmtUser.scope.slice(1)} scope`
    : (superAdmin?.superadmin_role ? ROLE_LABELS[superAdmin.superadmin_role] ?? superAdmin.superadmin_role : undefined)

  const closeSidebar = () => setSidebarOpen(false)

  const sidebarContent = (
    <>
      <div className="px-4 py-5 border-b border-white/10">
        <span className="font-serif font-bold text-lg text-white">ZedRead</span>
        <p className="text-xs text-white/50 mt-0.5">
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
            {superAdmin.superadmin_role === 'admin' && (
              <>
                <div className="pt-3 pb-1 px-3 text-xs font-medium text-white/40 uppercase tracking-wide">
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
                <div className="pt-3 pb-1 px-3 text-xs font-medium text-white/40 uppercase tracking-wide">
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

      <div className="px-4 py-4 border-t border-white/10">
        <p className="text-xs text-white/60 truncate">{user?.email}</p>
        <p className="text-xs text-white/40 capitalize">{scopeLabel}</p>
        <div className="mt-2 flex items-center gap-3">
          <button
            onClick={() => { setShowChangePassword(true); closeSidebar() }}
            className="text-xs text-white/70 hover:text-white transition-colors"
          >
            Change password
          </button>
          <button
            onClick={logout}
            className="text-xs text-red-300 hover:text-red-100 transition-colors"
          >
            Sign out
          </button>
          <button
            onClick={toggleTheme}
            title="Toggle theme"
            aria-label="Toggle theme"
            className="ml-auto w-7 h-7 flex items-center justify-center rounded-md border border-white/20 text-white/70 hover:text-white text-sm"
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
      <aside className="hidden sm:flex w-56 bg-[var(--zr-sidebar)] border-r border-white/10 flex-col">
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
        className={`fixed inset-y-0 left-0 z-50 w-56 bg-[var(--zr-sidebar)] border-r border-white/10 flex flex-col transform transition-transform duration-200 sm:hidden ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {sidebarContent}
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto bg-[var(--zr-bg)] min-w-0">
        {/* Mobile header bar with hamburger */}
        <div className="flex items-center gap-3 px-4 py-3 bg-[var(--zr-sidebar)] border-b border-white/10 sm:hidden">
          <button
            onClick={() => setSidebarOpen(true)}
            className="p-1 text-white/70 hover:text-white"
            aria-label="Open menu"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <span className="font-serif font-bold text-white text-base">ZedRead</span>
        </div>
        <ImpersonationBanner />
        <Outlet />
      </main>
    </div>
  )
}
