/** Forgot-password page — requests a reset email for a portal user. */

import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/axios'

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [sent, setSent] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      await api.post('/auth/portal/forgot-password', { email })
      // Always show the same confirmation, regardless of whether the email
      // matched an account — avoids leaking which emails are registered.
      setSent(true)
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Something went wrong. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900 p-4 sm:p-6">
      <div className="w-full max-w-sm">
        <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-sm border border-gray-200 dark:border-gray-700 p-8">
          <div className="mb-6 text-center">
            <h1 className="text-brand-800 mb-0.5" style={{ fontFamily: "'Lora', serif", fontSize: '2rem', fontWeight: 700 }}>ZedRead</h1>
            <p className="text-gray-400 dark:text-gray-500 tracking-widest uppercase" style={{ fontSize: '0.6rem' }}>POS You Can Count On</p>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-4">Reset your password</p>
          </div>

          {sent ? (
            <div className="space-y-4 text-center">
              <p className="text-sm text-gray-600 dark:text-gray-400">
                If an account exists for <strong>{email}</strong>, a password reset link has
                been sent. Check your inbox.
              </p>
              <Link to="/login" className="text-xs text-brand-600 hover:underline">
                Back to sign in
              </Link>
            </div>
          ) : (
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
                {loading ? 'Sending…' : 'Send reset link'}
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
