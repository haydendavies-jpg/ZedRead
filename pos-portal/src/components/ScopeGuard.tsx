/**
 * Renders children only when the management JWT scope meets the minimum level.
 * SuperAdmins always pass through. Management users are checked against
 * the required scope hierarchy: group > brand > site.
 */

import { useAuth, isMgmtUser, isSuperAdmin } from '../context/AuthContext'

const SCOPE_LEVEL: Record<string, number> = { site: 1, brand: 2, group: 3 }

interface Props {
  /** Minimum required scope for management users. */
  minScope: 'site' | 'brand' | 'group'
  children: React.ReactNode
}

export function ScopeGuard({ minScope, children }: Props) {
  const { user } = useAuth()

  if (!user) return null

  if (isSuperAdmin(user)) return <>{children}</>

  if (isMgmtUser(user)) {
    if (SCOPE_LEVEL[user.scope] >= SCOPE_LEVEL[minScope]) {
      return <>{children}</>
    }
    return (
      <div className="flex items-center justify-center h-64 text-sm text-gray-400 dark:text-gray-500">
        Not available at your access level ({user.scope} scope).
      </div>
    )
  }

  return null
}
