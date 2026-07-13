/** Group detail page for portal admins — shows the editable company profile for a Group. */

import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/axios'
import { CompanyProfileForm } from '../../components/CompanyProfileForm'
import { sessionInto } from '../../utils/impersonation'
import type { Group } from '../../types'

export function GroupDetailPage() {
  const { groupId } = useParams<{ groupId: string }>()
  const [sessionError, setSessionError] = useState<string | null>(null)
  const [isSessioning, setIsSessioning] = useState(false)

  const { data: group, isLoading } = useQuery<Group>({
    queryKey: ['group', groupId],
    queryFn: () => api.get(`/groups/${groupId}`).then((r) => r.data),
    enabled: !!groupId,
  })

  if (!groupId) return null

  const handleSessionInto = async () => {
    setSessionError(null)
    setIsSessioning(true)
    try {
      await sessionInto('group', groupId)
    } catch {
      setSessionError('Could not start session. Ensure the group has an active master user.')
    } finally {
      setIsSessioning(false)
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 sm:px-6 py-4 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400 mb-2">
          <Link to="/groups" className="hover:text-brand-600 transition-colors">
            Groups
          </Link>
          <span>/</span>
          <span className="text-gray-900 dark:text-gray-100 font-medium">
            {isLoading ? '…' : group?.name}
          </span>
        </div>

        {group && (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-4">
              <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">{group.name}</h1>
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${group.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400'}`}>
                {group.is_active ? 'active' : 'suspended'}
              </span>
            </div>
            <button
              onClick={handleSessionInto}
              disabled={isSessioning}
              className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-xs font-medium px-3 py-1.5 rounded-lg transition-colors"
            >
              {isSessioning ? 'Opening…' : 'Session into management portal'}
            </button>
          </div>
        )}
        {sessionError && <p className="text-xs text-red-600 mt-1">{sessionError}</p>}
      </div>

      <div className="flex-1 overflow-auto bg-gray-50 dark:bg-gray-900 p-4 sm:p-6">
        {group && (
          <CompanyProfileForm
            entityType="group"
            entity={group}
            inherited={{ logoUrl: null, logoSource: null, billingEmail: null, billingEmailSource: null }}
            invalidateKeys={[['group', groupId], ['groups']]}
          />
        )}
      </div>
    </div>
  )
}
