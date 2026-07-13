/** Guards routes that require authentication. Redirects to /login if not signed in. */

import { Navigate } from 'react-router-dom'
import { useAuth, isSuperAdmin } from '../context/AuthContext'

interface Props {
  children: React.ReactNode
  requireSuperAdmin?: boolean
}

export function PrivateRoute({ children, requireSuperAdmin = false }: Props) {
  const { user, isLoading } = useAuth()

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-gray-500 dark:text-gray-400">Loading…</div>
      </div>
    )
  }

  if (!user) return <Navigate to="/login" replace />

  if (requireSuperAdmin && !isSuperAdmin(user)) {
    return <Navigate to="/" replace />
  }

  return <>{children}</>
}
