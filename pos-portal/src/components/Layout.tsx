/** Application shell: sidebar nav + main content area. Adapts based on JWT type. */

import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth, isPortalUser, isMgmtUser } from '../context/AuthContext'
import { ChangePasswordModal } from '../pages/ChangePasswordPage'

const PORTAL_ADMIN_NAV = [
  { to: '/groups', label: 'Groups' },
  { to: '/brands', label: 'Brands' },
  { to: '/sites', label: 'Sites' },
  { to: '/licenses', label: 'Licenses' },
]

const PORTAL_SUPER_ADMIN_NAV = [
  { to: '/portal-users', label: 'Portal Users' },
  { to: '/pos-users', label: 'POS Users' },
]

/** Nav items shown to all management users. */
const MGMT_NAV = [
  { to: '/management/products', label: 'Products' },
  { to: '/management/categories', label: 'Categories' },
  { to: '/management/tax', label: 'Tax' },
  { to: '/management/reports', label: 'Reports' },
]

/** Nav items shown to brand/group scope management users only. */
const MGMT_BRAND_NAV = [
  { to: '/management/overrides', label: 'Site Overrides' },
  { to: '/management/users', label: 'Users & Grants' },
]

export function Layout() {
  const { user, logout } = useAuth()

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
      isActive
        ? 'bg-brand-50 text-brand-800'
        : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
    }`

  const [showChangePassword, setShowChangePassword] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const mgmtUser = isMgmtUser(user) ? user : null
  const portalUser = isPortalUser(user) ? user : null
  const isBrandOrGroupScope = mgmtUser && (mgmtUser.scope === 'brand' || mgmtUser.scope === 'group')

  const scopeLabel = mgmtUser
    ? `${mgmtUser.scope.charAt(0).toUpperCase() + mgmtUser.scope.slice(1)} scope`
    : portalUser?.role?.replace('_', ' ')

  const closeSidebar = () => setSidebarOpen(false)

  const sidebarContent = (
    <>
      <div className="px-4 py-5 border-b border-gray-100">
        <span className="font-semibold text-gray-900">ZedRead</span>
        <p className="text-xs text-gray-400 mt-0.5">
          {mgmtUser ? 'Management Portal' : 'Admin Portal'}
        </p>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1">
        {portalUser && (
          <>
            {PORTAL_ADMIN_NAV.map(({ to, label }) => (
              <NavLink key={to} to={to} className={linkClass} onClick={closeSidebar}>
                {label}
              </NavLink>
            ))}
            {portalUser.role === 'super_admin' && (
              <>
                <div className="pt-3 pb-1 px-3 text-xs font-medium text-gray-400 uppercase tracking-wide">
                  Admin
                </div>
                {PORTAL_SUPER_ADMIN_NAV.map(({ to, label }) => (
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
                <div className="pt-3 pb-1 px-3 text-xs font-medium text-gray-400 uppercase tracking-wide">
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

      <div className="px-4 py-4 border-t border-gray-100">
        <p className="text-xs text-gray-500 truncate">{user?.email}</p>
        <p className="text-xs text-gray-400 capitalize">{scopeLabel}</p>
        <div className="mt-2 flex gap-3">
          <button
            onClick={() => { setShowChangePassword(true); closeSidebar() }}
            className="text-xs text-brand-600 hover:text-brand-800 transition-colors"
          >
            Change password
          </button>
          <button
            onClick={logout}
            className="text-xs text-red-500 hover:text-red-700 transition-colors"
          >
            Sign out
          </button>
        </div>
      </div>

      {showChangePassword && (
        <ChangePasswordModal onClose={() => setShowChangePassword(false)} />
      )}
    </>
  )

  return (
    <div className="flex min-h-screen">
      {/* Desktop sidebar — always visible at sm+ */}
      <aside className="hidden sm:flex w-56 bg-white border-r border-gray-200 flex-col">
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
        className={`fixed inset-y-0 left-0 z-50 w-56 bg-white border-r border-gray-200 flex flex-col transform transition-transform duration-200 sm:hidden ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {sidebarContent}
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto bg-gray-50 min-w-0">
        {/* Mobile header bar with hamburger */}
        <div className="flex items-center gap-3 px-4 py-3 bg-white border-b border-gray-200 sm:hidden">
          <button
            onClick={() => setSidebarOpen(true)}
            className="p-1 text-gray-600 hover:text-gray-900"
            aria-label="Open menu"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <span className="font-semibold text-gray-900 text-sm">ZedRead</span>
        </div>
        <Outlet />
      </main>
    </div>
  )
}
