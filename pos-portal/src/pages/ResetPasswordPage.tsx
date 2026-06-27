/** Reset-password page — consumes the token from the emailed link to set a new password. */

import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api/axios'

export function ResetPasswordPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const token = searchParams.get('token') ?? ''

  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [done, setDone] = useState(false)

  const mismatch = confirm.length > 0 && confirm !== password

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (mismatch || !token) return
    setLoading(true)
    setError(null)
    try {
      await api.post('/auth/portal/reset-password', { token, new_password: password })
      setDone(true)
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Failed to reset password. The link may have expired.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4 sm:p-6">
      <div className="w-full max-w-sm">
        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
          <div className="mb-6 text-center">
            <h1 className="text-brand-800 mb-0.5" style={{ fontFamily: "'Lora', serif", fontSize: '2rem', fontWeight: 700 }}>ZedRead</h1>
            <p className="text-gray-400 tracking-widest uppercase" style={{ fontSize: '0.6rem' }}>POS You Can Count On</p>
            <p className="text-sm text-gray-500 mt-4">Choose a new password</p>
          </div>

          {!token ? (
            <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              This reset link is missing its token. Please request a new one.
            </p>
          ) : done ? (
            <div className="space-y-4 text-center">
              <p className="text-sm text-gray-600">Your password has been updated.</p>
              <button
                onClick={() => navigate('/login')}
                className="w-full bg-brand-600 hover:bg-brand-700 text-white font-medium py-2 px-4 rounded-lg text-sm transition-colors"
              >
                Sign in
              </button>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">New Password</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  autoFocus
                  minLength={8}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                  placeholder="Min 8 characters"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Confirm New Password</label>
                <input
                  type="password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  required
                  className={`w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 ${
                    mismatch ? 'border-red-400' : 'border-gray-300'
                  }`}
                />
                {mismatch && <p className="text-xs text-red-600 mt-1">Passwords do not match.</p>}
              </div>

              {error && (
                <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                  {error}
                </p>
              )}

              <button
                type="submit"
                disabled={loading || mismatch || !password || !confirm}
                className="w-full bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white font-medium py-2 px-4 rounded-lg text-sm transition-colors"
              >
                {loading ? 'Saving…' : 'Reset password'}
              </button>

              <p className="text-center">
                <Link to="/login" className="text-xs text-brand-600 hover:underline">
                  Back to sign in
                </Link>
              </p>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}
