/** Guards routes that require authentication. Redirects to /login if not signed in. */

import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

interface Props {
  children: React.ReactNode
  requireSuperAdmin?: boolean
}

export function PrivateRoute({ children, requireSuperAdmin = false }: Props) {
  const { user, isLoading } = useAuth()

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-gray-500">Loading…</div>
      </div>
    )
  }

  if (!user) return <Navigate to="/login" replace />

  if (requireSuperAdmin && user.role !== 'super_admin') {
    return <Navigate to="/" replace />
  }

  return <>{children}</>
}
