/** Banner shown at the top of every management page during admin impersonation. */

import { useAuth } from '../context/AuthContext'

export function ImpersonationBanner() {
  const { isImpersonated, impersonatorName, user } = useAuth()

  if (!isImpersonated) return null

  return (
    <div className="flex items-center justify-between gap-3 px-4 py-2 bg-amber-50 border-b border-amber-200 text-xs text-amber-800">
      <span>
        Viewing as <strong>{user?.name}</strong> — actions logged as{' '}
        <strong>{impersonatorName}</strong>
      </span>
      <button
        onClick={() => window.close()}
        className="px-2 py-0.5 rounded border border-amber-300 hover:bg-amber-100 transition-colors font-medium"
      >
        Exit
      </button>
    </div>
  )
}
