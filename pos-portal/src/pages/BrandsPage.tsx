/** CRUD page for Brands (second tier of the hierarchy). */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/axios'
import type { Brand, Group } from '../types'
import { Link } from 'react-router-dom'
import { EntityIdChip } from '../components/EntityIdChip'
import { StatusBadge } from '../components/StatusBadge'
import { Modal } from '../components/Modal'
import { CompanyProfileFields, type CompanyProfileValues } from '../components/CompanyProfileFields'
import { DEFAULT_COMPANY_PROFILE_VALUES, confirmCurrencyChange } from '../utils/companyProfile'

async function fetchBrands(): Promise<Brand[]> {
  const { data } = await api.get('/brands/', { params: { limit: 200 } })
  return data
}

async function fetchGroups(): Promise<Group[]> {
  const { data } = await api.get('/groups/', { params: { limit: 200 } })
  return data
}

export function BrandsPage() {
  const qc = useQueryClient()
  const { data: brands = [], isLoading } = useQuery({ queryKey: ['brands'], queryFn: fetchBrands })
  const { data: groups = [] } = useQuery({ queryKey: ['groups'], queryFn: fetchGroups })

  const [search, setSearch] = useState('')
  const [groupFilter, setGroupFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState<Brand | null>(null)
  const [name, setName] = useState('')
  const [groupId, setGroupId] = useState('')
  const [masterEmail, setMasterEmail] = useState('')
  const [masterPassword, setMasterPassword] = useState('')
  const [profile, setProfile] = useState<CompanyProfileValues>(DEFAULT_COMPANY_PROFILE_VALUES)
  const [formError, setFormError] = useState<string | null>(null)
  const [sessioningId, setSessioningId] = useState<string | null>(null)

  const invalidate = () => qc.invalidateQueries({ queryKey: ['brands'] })

  const handleSessionInto = async (brandId: string) => {
    setSessioningId(brandId)
    try {
      const { data: grantData } = await api.get<{ grant_id: string }>('/admin/master-grant', {
        params: { brand_id: brandId },
      })
      const { data: tokenData } = await api.post<{ access_token: string }>('/admin/impersonate', {
        grant_id: grantData.grant_id,
      })
      sessionStorage.setItem('imp_token', tokenData.access_token)
      window.open('/management', '_blank')
    } catch {
      // error is surfaced on the brand detail page
    } finally {
      setSessioningId(null)
    }
  }

  const createMutation = useMutation({
    mutationFn: (body: { name: string; group_id: string; master_email: string; master_password: string } & CompanyProfileValues) =>
      api.post('/brands/', body),
    onSuccess: () => { invalidate(); setShowCreate(false); setName(''); setGroupId(''); setMasterEmail(''); setMasterPassword(''); setProfile(DEFAULT_COMPANY_PROFILE_VALUES) },
    onError: () => { invalidate(); setFormError('Failed to create brand.') },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: { name: string } & CompanyProfileValues }) =>
      api.patch(`/brands/${id}`, body),
    onSuccess: () => { invalidate(); setEditing(null); setName('') },
    onError: () => { invalidate(); setFormError('Failed to update brand.') },
  })

  const suspendMutation = useMutation({
    mutationFn: (id: string) => api.post(`/brands/${id}/suspend`),
    onSuccess: invalidate,
  })

  const activateMutation = useMutation({
    mutationFn: (id: string) => api.post(`/brands/${id}/activate`),
    onSuccess: invalidate,
  })

  const groupName = (id: string) => groups.find((g) => g.id === id)?.name ?? id.slice(0, 8)

  const openCreate = () => {
    setName('')
    setGroupId(groups[0]?.id ?? '')
    setMasterEmail('')
    setMasterPassword('')
    setProfile(DEFAULT_COMPANY_PROFILE_VALUES)
    setFormError(null)
    setShowCreate(true)
  }
  const openEdit = (b: Brand) => {
    setName(b.name)
    setProfile({
      timezone: b.timezone,
      currency: b.currency,
      country: b.country,
      tax_id_value: b.tax_id_value ?? '',
      billing_email: b.billing_email ?? '',
    })
    setFormError(null)
    setEditing(b)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)
    if (editing) {
      if (!confirmCurrencyChange(editing.currency, profile.currency, 'brand')) return
      updateMutation.mutate({ id: editing.id, body: { name, ...profile } })
    } else {
      createMutation.mutate({ name, group_id: groupId, master_email: masterEmail, master_password: masterPassword, ...profile })
    }
  }

  const filtered = brands.filter((b) => {
    if (search && !b.name.toLowerCase().includes(search.toLowerCase())) return false
    if (groupFilter && b.group_id !== groupFilter) return false
    if (statusFilter === 'active' && !b.is_active) return false
    if (statusFilter === 'suspended' && b.is_active) return false
    return true
  })

  const hasFilters = search || groupFilter || statusFilter

  return (
    <div className="p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <h1 className="text-xl font-semibold text-gray-900">Brands</h1>
        <button
          onClick={openCreate}
          className="bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          + New Brand
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-3 mb-4">
        <input
          type="text"
          placeholder="Search by name…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 w-56"
        />
        <select
          value={groupFilter}
          onChange={(e) => setGroupFilter(e.target.value)}
          className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
        >
          <option value="">All groups</option>
          {groups.map((g) => (
            <option key={g.id} value={g.id}>{g.name}</option>
          ))}
        </select>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
        >
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="suspended">Suspended</option>
        </select>
        {hasFilters && (
          <button
            onClick={() => { setSearch(''); setGroupFilter(''); setStatusFilter('') }}
            className="text-xs text-gray-400 hover:text-gray-600"
          >
            Clear filters
          </button>
        )}
        <span className="text-xs text-gray-400 ml-auto">
          {filtered.length} of {brands.length}
        </span>
      </div>

      {isLoading ? (
        <div className="text-gray-400 text-sm">Loading…</div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-gray-200">
          <table className="w-full text-sm min-w-[600px]">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                <th className="px-4 py-3">ID</th>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Group ID</th>
                <th className="px-4 py-3">Group</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {filtered.map((b) => (
                <tr key={b.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3"><EntityIdChip id={b.id} ref={b.ref} /></td>
                  <td className="px-4 py-3 font-medium text-gray-900">
                    <Link to={`/brands/${b.id}`} className="hover:text-brand-600 transition-colors">
                      {b.name}
                    </Link>
                  </td>
                  <td className="px-4 py-3"><EntityIdChip id={b.group_id} ref={groups.find((g) => g.id === b.group_id)?.ref} /></td>
                  <td className="px-4 py-3 text-gray-500">{groupName(b.group_id)}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={b.is_active ? 'active' : 'suspended'} />
                  </td>
                  <td className="px-4 py-3 flex gap-2">
                    <button onClick={() => openEdit(b)} className="text-brand-600 hover:underline text-xs">Edit</button>
                    {b.is_active ? (
                      <button onClick={() => suspendMutation.mutate(b.id)} className="text-amber-600 hover:underline text-xs">Suspend</button>
                    ) : (
                      <button onClick={() => activateMutation.mutate(b.id)} className="text-green-600 hover:underline text-xs">Activate</button>
                    )}
                    <button
                      onClick={() => handleSessionInto(b.id)}
                      disabled={sessioningId === b.id}
                      className="text-brand-600 hover:underline text-xs disabled:opacity-50"
                    >
                      {sessioningId === b.id ? '…' : 'Session into'}
                    </button>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                  {brands.length === 0 ? 'No brands yet.' : 'No brands match the current filters.'}
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {(showCreate || editing) && (
        <Modal
          title={editing ? 'Edit Brand' : 'New Brand'}
          onClose={() => { setShowCreate(false); setEditing(null) }}
        >
          <form onSubmit={handleSubmit} className="space-y-4">
            {!editing && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Group</label>
                <select
                  value={groupId}
                  onChange={(e) => setGroupId(e.target.value)}
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                >
                  {groups.map((g) => (
                    <option key={g.id} value={g.id}>{g.name}</option>
                  ))}
                </select>
              </div>
            )}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                autoFocus
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                placeholder="Burger Chain"
              />
            </div>
            {!editing && (
              <>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Brand email</label>
                  <input
                    type="email"
                    value={masterEmail}
                    onChange={(e) => setMasterEmail(e.target.value)}
                    required
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                    placeholder="owner@example.com"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Password (min 8 chars)</label>
                  <input
                    type="password"
                    value={masterPassword}
                    onChange={(e) => setMasterPassword(e.target.value)}
                    required
                    minLength={8}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                  />
                </div>
              </>
            )}
            <CompanyProfileFields values={profile} onChange={setProfile} />
            {formError && <p className="text-sm text-red-600">{formError}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => { setShowCreate(false); setEditing(null) }} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800">Cancel</button>
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
