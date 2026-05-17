/** Application shell: sidebar nav + main content area. Adapts based on JWT type. */

import { NavLink, Outlet } from 'react-router-dom'
import { useAuth, isPortalUser, isMgmtUser } from '../context/AuthContext'

const PORTAL_ADMIN_NAV = [
  { to: '/groups', label: 'Groups' },
  { to: '/brands', label: 'Brands' },
  { to: '/sites', label: 'Sites' },
  { to: '/licenses', label: 'Licenses' },
]

const PORTAL_SUPER_ADMIN_NAV = [{ to: '/portal-users', label: 'Portal Users' }]

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

  const mgmtUser = isMgmtUser(user) ? user : null
  const portalUser = isPortalUser(user) ? user : null
  const isBrandOrGroupScope = mgmtUser && (mgmtUser.scope === 'brand' || mgmtUser.scope === 'group')

  const scopeLabel = mgmtUser
    ? `${mgmtUser.scope.charAt(0).toUpperCase() + mgmtUser.scope.slice(1)} scope`
    : portalUser?.role?.replace('_', ' ')

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="w-56 bg-white border-r border-gray-200 flex flex-col">
        <div className="px-4 py-5 border-b border-gray-100">
          <span className="font-semibold text-gray-900">ZedRead</span>
          <p className="text-xs text-gray-400 mt-0.5">
            {mgmtUser ? 'Management Portal' : 'Admin Portal'}
          </p>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-1">
          {/* Portal admin nav */}
          {portalUser && (
            <>
              {PORTAL_ADMIN_NAV.map(({ to, label }) => (
                <NavLink key={to} to={to} className={linkClass}>
                  {label}
                </NavLink>
              ))}

              {portalUser.role === 'super_admin' && (
                <>
                  <div className="pt-3 pb-1 px-3 text-xs font-medium text-gray-400 uppercase tracking-wide">
                    Admin
                  </div>
                  {PORTAL_SUPER_ADMIN_NAV.map(({ to, label }) => (
                    <NavLink key={to} to={to} className={linkClass}>
                      {label}
                    </NavLink>
                  ))}
                </>
              )}
            </>
          )}

          {/* Management nav */}
          {mgmtUser && (
            <>
              {MGMT_NAV.map(({ to, label }) => (
                <NavLink key={to} to={to} className={linkClass}>
                  {label}
                </NavLink>
              ))}

              {isBrandOrGroupScope && (
                <>
                  <div className="pt-3 pb-1 px-3 text-xs font-medium text-gray-400 uppercase tracking-wide">
                    Users
                  </div>
                  {MGMT_BRAND_NAV.map(({ to, label }) => (
                    <NavLink key={to} to={to} className={linkClass}>
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
          <button
            onClick={logout}
            className="mt-2 text-xs text-red-500 hover:text-red-700 transition-colors"
          >
            Sign out
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto bg-gray-50">
        <Outlet />
      </main>
    </div>
  )
}
