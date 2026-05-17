/** Portal login page — handles portal users and multi-grant POS manager scope selection. */

import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import type { GrantSummary } from '../types'

export function LoginPage() {
  const { login, selectGrant, pendingGrants } = useAuth()
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
      await login(email, password)
      // pendingGrants will be non-null if multi-grant — handled below without navigating
      if (!pendingGrants) navigate('/')
    } catch {
      setError('Invalid email or password.')
    } finally {
      setLoading(false)
    }
  }

  // After login() resolves with available_grants, pendingGrants becomes non-null
  // We re-check here after state update (component re-renders)
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

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="w-full max-w-sm">
        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
          <div className="mb-6 text-center">
            <h1 className="text-brand-800 mb-0.5" style={{ fontFamily: "'Lora', serif", fontSize: '2rem', fontWeight: 700 }}>ZedRead</h1>
            <p className="text-gray-400 tracking-widest uppercase" style={{ fontSize: '0.6rem' }}>POS You Can Count On</p>
            <p className="text-sm text-gray-500 mt-4">Sign in to Portal</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoFocus
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                placeholder="admin@example.com"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
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

/** Shown when a POS user has multiple portal-capable grants; pick one context. */
function GrantSelectorView({ grants, onSelect, loading, error }: GrantSelectorViewProps) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="w-full max-w-sm">
        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
          <h1 className="text-xl font-semibold text-gray-900 mb-1">Select access context</h1>
          <p className="text-sm text-gray-500 mb-6">
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
                className="w-full text-left px-4 py-3 border border-gray-200 rounded-lg hover:border-indigo-400 hover:bg-indigo-50 disabled:opacity-50 transition-colors"
              >
                <p className="text-sm font-medium text-gray-900">{g.scope_name}</p>
                <p className="text-xs text-gray-500 mt-0.5 capitalize">
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
