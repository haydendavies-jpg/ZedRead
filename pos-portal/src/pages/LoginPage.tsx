/** Portal login page — handles SuperAdmin and multi-grant Manager scope selection. */

import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { apiErrorMessage } from '../utils/apiError'
import type { GrantSummary, IdentitySummary } from '../types'

/**
 * Map a failed login request to a user-facing message.
 *
 * A 503 means the API reached us but couldn't reach the database — most
 * commonly a paused Supabase project — so it gets a distinct message instead
 * of being lumped in with "wrong password". No response at all (network
 * error, proxy timeout) gets the same treatment since it's usually the same
 * root cause manifesting before the API can even respond.
 */
function loginErrorMessage(err: unknown): string {
  const status = (err as { response?: { status?: number } })?.response?.status
  if (status === 503) {
    return apiErrorMessage(
      err,
      'The database is temporarily unavailable. If this persists, the Supabase project may be paused.'
    )
  }
  if (!(err as { response?: unknown })?.response) {
    return 'Could not reach the server. Please check your connection and try again.'
  }
  return apiErrorMessage(err, 'Invalid email or password.')
}

export function LoginPage() {
  const { login, selectGrant, selectIdentity, pendingGrants, pendingIdentities } = useAuth()
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const result = await login(email, password)
      // 'direct' → tokens issued; navigate to dashboard
      // 'grant_selection' → pendingGrants set; LoginPage re-renders with GrantSelectorView
      if (result === 'direct') navigate('/')
    } catch (err: unknown) {
      setError(loginErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  // After login() resolves with available_grants, pendingGrants becomes non-null.
  // Checked before pendingIdentities: picking a User identity with multiple
  // grants clears pendingIdentities and sets pendingGrants for a follow-up step.
  if (pendingGrants) {
    return (
      <GrantSelectorView
        grants={pendingGrants}
        password={password}
        onSelect={async (grant) => {
          setLoading(true)
          setError(null)
          try {
            await selectGrant(grant.grant_id, password)
            navigate('/')
          } catch {
            setError('Failed to select access context. Please try again.')
          } finally {
            setLoading(false)
          }
        }}
        loading={loading}
        error={error}
      />
    )
  }

  // Email matched both a SuperAdmin and a portal-capable User — let them pick
  // which platform to enter (ROLE_MODEL.md §3).
  if (pendingIdentities) {
    return (
      <IdentitySelectorView
        identities={pendingIdentities}
        onSelect={async (identity) => {
          setLoading(true)
          setError(null)
          try {
            const result = await selectIdentity(identity.identity_type, email, password)
            // 'grant_selection' → pendingGrants set; component re-renders with GrantSelectorView
            if (result === 'direct') navigate('/')
          } catch {
            setError('Failed to open the selected identity. Please try again.')
          } finally {
            setLoading(false)
          }
        }}
        loading={loading}
        error={error}
      />
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
      <div className="w-full max-w-sm">
        <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-sm border border-gray-200 dark:border-gray-700 p-8">
          <div className="mb-6 text-center">
            <h1 className="text-brand-800 mb-0.5" style={{ fontFamily: "'Lora', serif", fontSize: '2rem', fontWeight: 700 }}>ZedRead</h1>
            <p className="text-gray-400 dark:text-gray-500 tracking-widest uppercase" style={{ fontSize: '0.6rem' }}>POS You Can Count On</p>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-4">Sign in to Portal</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoFocus
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                placeholder="admin@example.com"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                placeholder="••••••••••••"
              />
            </div>

            {error && (
              <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white font-medium py-2 px-4 rounded-lg text-sm transition-colors"
            >
              {loading ? 'Signing in…' : 'Sign in'}
            </button>

            <p className="text-center">
              <Link to="/forgot-password" className="text-xs text-brand-600 hover:underline">
                Forgot password?
              </Link>
            </p>
          </form>
        </div>
      </div>
    </div>
  )
}

// ── Scope selector ─────────────────────────────────────────────────────────────

interface GrantSelectorViewProps {
  grants: GrantSummary[]
  password: string
  onSelect: (grant: GrantSummary) => void
  loading: boolean
  error: string | null
}

// ── Identity selector ──────────────────────────────────────────────────────────

interface IdentitySelectorViewProps {
  identities: IdentitySummary[]
  onSelect: (identity: IdentitySummary) => void
  loading: boolean
  error: string | null
}

/** Shown when an email is shared by a SuperAdmin and a User; pick which to enter. */
function IdentitySelectorView({ identities, onSelect, loading, error }: IdentitySelectorViewProps) {
  // Human-readable label for each identity_type — the platform the choice opens.
  const platformLabel: Record<IdentitySummary['identity_type'], string> = {
    superadmin: 'Admin Portal',
    user: 'Management Portal',
  }
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
      <div className="w-full max-w-sm">
        <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-sm border border-gray-200 dark:border-gray-700 p-8">
          <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-1">Choose where to sign in</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
            This email is registered for more than one platform. Choose which to open.
          </p>

          {error && (
            <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2 mb-4">
              {error}
            </p>
          )}

          <div className="space-y-2">
            {identities.map((identity) => (
              <button
                key={identity.identity_type}
                onClick={() => onSelect(identity)}
                disabled={loading}
                className="w-full text-left px-4 py-3 border border-gray-200 dark:border-gray-700 rounded-lg hover:border-brand-500 hover:bg-brand-50 disabled:opacity-50 transition-colors"
              >
                <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{platformLabel[identity.identity_type]}</p>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{identity.display_name}</p>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

/** Shown when a POS user has multiple portal-capable grants; pick one context. */
function GrantSelectorView({ grants, onSelect, loading, error }: GrantSelectorViewProps) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
      <div className="w-full max-w-sm">
        <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-sm border border-gray-200 dark:border-gray-700 p-8">
          <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-1">Select access context</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
            You have access to multiple areas. Choose which context to open.
          </p>

          {error && (
            <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2 mb-4">
              {error}
            </p>
          )}

          <div className="space-y-2">
            {grants.map((g) => (
              <button
                key={g.grant_id}
                onClick={() => onSelect(g)}
                disabled={loading}
                className="w-full text-left px-4 py-3 border border-gray-200 dark:border-gray-700 rounded-lg hover:border-brand-500 hover:bg-brand-50 disabled:opacity-50 transition-colors"
              >
                <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{g.scope_name}</p>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 capitalize">
                  {g.scope} scope · {g.access_profile_name}
                </p>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
