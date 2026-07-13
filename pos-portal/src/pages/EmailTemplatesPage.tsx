/** SuperAdmin-only CRUD page for email templates (e.g. the billing-info-request email). */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/axios'
import type { EmailTemplate } from '../types'
import { EntityIdChip } from '../components/EntityIdChip'
import { Modal } from '../components/Modal'

async function fetchEmailTemplates(): Promise<EmailTemplate[]> {
  const { data } = await api.get('/email-templates/', { params: { limit: 200 } })
  return data
}

const DEFAULT_FORM = { template_key: '', name: '', subject: '', body: '' }

export function EmailTemplatesPage() {
  const qc = useQueryClient()
  const { data: templates = [], isLoading } = useQuery({ queryKey: ['email-templates'], queryFn: fetchEmailTemplates })

  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState<EmailTemplate | null>(null)
  const [form, setForm] = useState(DEFAULT_FORM)
  const [formError, setFormError] = useState<string | null>(null)

  const invalidate = () => qc.invalidateQueries({ queryKey: ['email-templates'] })

  const createMutation = useMutation({
    mutationFn: (body: typeof DEFAULT_FORM) => api.post('/email-templates/', body),
    onSuccess: () => { invalidate(); setShowCreate(false); setForm(DEFAULT_FORM) },
    onError: (e: unknown) => {
      invalidate()
      const msg = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
      setFormError(msg ?? 'Failed to create email template.')
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: { name: string; subject: string; body: string; is_active: boolean } }) =>
      api.patch(`/email-templates/${id}`, body),
    onSuccess: () => { invalidate(); setEditing(null) },
    onError: (e: unknown) => {
      invalidate()
      const msg = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
      setFormError(msg ?? 'Failed to update email template.')
    },
  })

  const openCreate = () => {
    setForm(DEFAULT_FORM)
    setFormError(null)
    setShowCreate(true)
  }
  const openEdit = (t: EmailTemplate) => {
    setForm({ template_key: t.template_key, name: t.name, subject: t.subject, body: t.body })
    setFormError(null)
    setEditing(t)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)
    if (editing) {
      updateMutation.mutate({
        id: editing.id,
        body: { name: form.name, subject: form.subject, body: form.body, is_active: editing.is_active },
      })
    } else {
      createMutation.mutate(form)
    }
  }

  const toggleActive = (t: EmailTemplate) => {
    setFormError(null)
    updateMutation.mutate({ id: t.id, body: { name: t.name, subject: t.subject, body: t.body, is_active: !t.is_active } })
  }

  return (
    <div className="p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Email Templates</h1>
        <button
          onClick={openCreate}
          className="bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          + New Template
        </button>
      </div>

      {isLoading ? (
        <div className="text-gray-400 dark:text-gray-500 text-sm">Loading…</div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-gray-200 dark:border-gray-700">
          <table className="w-full text-sm min-w-[640px]">
            <thead>
              <tr className="border-b border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-900 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                <th className="px-4 py-3">ID</th>
                <th className="px-4 py-3">Key</th>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Subject</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {templates.map((t) => (
                <tr key={t.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/60">
                  <td className="px-4 py-3"><EntityIdChip id={t.id} /></td>
                  <td className="px-4 py-3 font-mono text-xs text-gray-600 dark:text-gray-400">
                    {t.template_key}
                    {t.is_system && <span className="ml-1 text-xs text-brand-500">(system)</span>}
                  </td>
                  <td className="px-4 py-3 font-medium text-gray-900 dark:text-gray-100">{t.name}</td>
                  <td className="px-4 py-3 text-gray-500 dark:text-gray-400">{t.subject}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${t.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400'}`}>
                      {t.is_active ? 'active' : 'inactive'}
                    </span>
                  </td>
                  <td className="px-4 py-3 flex gap-2">
                    <button onClick={() => openEdit(t)} className="text-brand-600 hover:underline text-xs">Edit</button>
                    <button onClick={() => toggleActive(t)} className="text-amber-600 hover:underline text-xs">
                      {t.is_active ? 'Deactivate' : 'Activate'}
                    </button>
                  </td>
                </tr>
              ))}
              {templates.length === 0 && (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-400 dark:text-gray-500">No email templates yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {(showCreate || editing) && (
        <Modal
          title={editing ? 'Edit Email Template' : 'New Email Template'}
          onClose={() => { setShowCreate(false); setEditing(null) }}
        >
          <form onSubmit={handleSubmit} className="space-y-4">
            {!editing && (
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Template key</label>
                <input
                  value={form.template_key}
                  onChange={(e) => setForm({ ...form, template_key: e.target.value })}
                  required
                  autoFocus
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                  placeholder="billing_info_request"
                />
              </div>
            )}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Name</label>
              <input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                required
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Subject</label>
              <input
                value={form.subject}
                onChange={(e) => setForm({ ...form, subject: e.target.value })}
                required
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Body</label>
              <textarea
                value={form.body}
                onChange={(e) => setForm({ ...form, body: e.target.value })}
                required
                rows={6}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                placeholder="Hi, please send billing info for $entity_name ($entity_type)…"
              />
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">Use $entity_name and $entity_type as placeholders.</p>
            </div>
            {formError && <p className="text-sm text-red-600">{formError}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => { setShowCreate(false); setEditing(null) }} className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-800">Cancel</button>
              <button type="submit" disabled={createMutation.isPending || updateMutation.isPending} className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg">
                {editing ? 'Save' : 'Create'}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
