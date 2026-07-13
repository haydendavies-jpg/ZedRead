/** Change password modal — accessible from the sidebar for all logged-in portal users. */

import { useState } from 'react'
import { api } from '../api/axios'
import { Modal } from '../components/Modal'

interface Props {
  onClose: () => void
}

export function ChangePasswordModal({ onClose }: Props) {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const [loading, setLoading] = useState(false)

  const mismatch = confirm.length > 0 && confirm !== next

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (mismatch) return
    setError(null)
    setLoading(true)
    try {
      await api.post('/auth/portal/change-password', {
        current_password: current,
        new_password: next,
      })
      setSuccess(true)
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Failed to change password.')
    } finally {
      setLoading(false)
    }
  }

  if (success) {
    return (
      <Modal title="Password Changed" onClose={onClose}>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">
          Your password has been updated successfully.
        </p>
        <div className="flex justify-end">
          <button
            onClick={onClose}
            className="bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium px-4 py-2 rounded-lg"
          >
            Done
          </button>
        </div>
      </Modal>
    )
  }

  return (
    <Modal title="Change Password" onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Current Password
          </label>
          <input
            type="password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            required
            autoFocus
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            New Password
          </label>
          <input
            type="password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            required
            minLength={8}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            placeholder="Min 8 characters"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Confirm New Password
          </label>
          <input
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
            className={`w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 ${
              mismatch ? 'border-red-400' : 'border-gray-300 dark:border-gray-600'
            }`}
          />
          {mismatch && (
            <p className="text-xs text-red-600 mt-1">Passwords do not match.</p>
          )}
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-800"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={loading || mismatch || !current || !next || !confirm}
            className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg"
          >
            {loading ? 'Saving…' : 'Change Password'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
