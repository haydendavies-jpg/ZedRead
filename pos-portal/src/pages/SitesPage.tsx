/** CRUD page for Sites (third tier of the hierarchy). */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../api/axios'
import type { Brand, Site } from '../types'
import { EntityIdChip } from '../components/EntityIdChip'
import { StatusBadge } from '../components/StatusBadge'
import { Modal } from '../components/Modal'
import { CompanyProfileFields, type CompanyProfileValues } from '../components/CompanyProfileFields'
import { DEFAULT_COMPANY_PROFILE_VALUES, confirmCurrencyChange } from '../utils/companyProfile'
import { apiErrorMessage } from '../utils/apiError'
import { sessionInto } from '../utils/impersonation'
import { useAddressSearch } from '../hooks/useAddressSearch'

interface AddressValues {
  address_street: string
  address_city: string
  address_state: string
  address_postcode: string
}

const DEFAULT_ADDRESS_VALUES: AddressValues = { address_street: '', address_city: '', address_state: '', address_postcode: '' }

async function fetchSites(): Promise<Site[]> {
  const { data } = await api.get('/sites/', { params: { limit: 200 } })
  return data
}

async function fetchBrands(): Promise<Brand[]> {
  const { data } = await api.get('/brands/', { params: { limit: 200 } })
  return data
}

export function SitesPage() {
  const qc = useQueryClient()
  const { data: sites = [], isLoading } = useQuery({ queryKey: ['sites'], queryFn: fetchSites })
  const { data: brands = [] } = useQuery({ queryKey: ['brands'], queryFn: fetchBrands })

  const [search, setSearch] = useState('')
  const [brandFilter, setBrandFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState<Site | null>(null)
  const [name, setName] = useState('')
  const [brandId, setBrandId] = useState('')
  const [masterEmail, setMasterEmail] = useState('')
  const [masterPassword, setMasterPassword] = useState('')
  const [profile, setProfile] = useState<CompanyProfileValues>(DEFAULT_COMPANY_PROFILE_VALUES)
  const [address, setAddress] = useState<AddressValues>(DEFAULT_ADDRESS_VALUES)
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [sessioningId, setSessioningId] = useState<string | null>(null)
  const [formError, setFormError] = useState<string | null>(null)

  const { suggestions } = useAddressSearch(showCreate && !editing ? address.address_street : '')

  const invalidate = () => qc.invalidateQueries({ queryKey: ['sites'] })

  const createMutation = useMutation({
    mutationFn: (body: { name: string; brand_id: string; master_email: string; master_password: string } & CompanyProfileValues & AddressValues) =>
      api.post('/sites/', body),
    onSuccess: () => {
      invalidate()
      setShowCreate(false)
      setName('')
      setBrandId('')
      setMasterEmail('')
      setMasterPassword('')
      setProfile(DEFAULT_COMPANY_PROFILE_VALUES)
      setAddress(DEFAULT_ADDRESS_VALUES)
    },
    onError: (e: unknown) => { invalidate(); setFormError(apiErrorMessage(e, 'Failed to create site.')) },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: { name: string } & CompanyProfileValues & AddressValues }) =>
      api.patch(`/sites/${id}`, body),
    onSuccess: () => { invalidate(); setEditing(null); setName('') },
    onError: (e: unknown) => { invalidate(); setFormError(apiErrorMessage(e, 'Failed to update site.')) },
  })

  const suspendMutation = useMutation({
    mutationFn: (id: string) => api.post(`/sites/${id}/suspend`),
    onSuccess: invalidate,
  })

  const activateMutation = useMutation({
    mutationFn: (id: string) => api.post(`/sites/${id}/activate`),
    onSuccess: invalidate,
  })

  const handleSessionInto = async (siteId: string) => {
    setSessioningId(siteId)
    try {
      await sessionInto('site', siteId)
    } catch {
      // error shown on the detail page; silently clear loading state here
    } finally {
      setSessioningId(null)
    }
  }

  const brandName = (id: string) => brands.find((b) => b.id === id)?.name ?? id.slice(0, 8)

  const openCreate = () => {
    setName('')
    setBrandId(brands[0]?.id ?? '')
    setMasterEmail('')
    setMasterPassword('')
    setProfile(DEFAULT_COMPANY_PROFILE_VALUES)
    setAddress(DEFAULT_ADDRESS_VALUES)
    setFormError(null)
    setShowCreate(true)
  }
  const openEdit = (s: Site) => {
    setName(s.name)
    setProfile({
      timezone: s.timezone,
      currency: s.currency,
      country: s.country,
      tax_id_value: s.tax_id_value ?? '',
      billing_email: s.billing_email ?? '',
    })
    setAddress({
      address_street: s.address_street,
      address_city: s.address_city ?? '',
      address_state: s.address_state,
      address_postcode: s.address_postcode,
    })
    setFormError(null)
    setEditing(s)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)
    if (editing) {
      if (!confirmCurrencyChange(editing.currency, profile.currency, 'site')) return
      updateMutation.mutate({ id: editing.id, body: { name, ...profile, ...address } })
    } else {
      createMutation.mutate({ name, brand_id: brandId, master_email: masterEmail, master_password: masterPassword, ...profile, ...address })
    }
  }

  const filtered = sites.filter((s) => {
    if (search && !s.name.toLowerCase().includes(search.toLowerCase())) return false
    if (brandFilter && s.brand_id !== brandFilter) return false
    if (statusFilter === 'active' && !s.is_active) return false
    if (statusFilter === 'suspended' && s.is_active) return false
    return true
  })

  const hasFilters = search || brandFilter || statusFilter

  return (
    <div className="p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <h1 className="text-xl font-semibold text-gray-900">Sites</h1>
        <button
          onClick={openCreate}
          className="bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          + New Site
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
          value={brandFilter}
          onChange={(e) => setBrandFilter(e.target.value)}
          className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
        >
          <option value="">All brands</option>
          {brands.map((b) => (
            <option key={b.id} value={b.id}>{b.name}</option>
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
            onClick={() => { setSearch(''); setBrandFilter(''); setStatusFilter('') }}
            className="text-xs text-gray-400 hover:text-gray-600"
          >
            Clear filters
          </button>
        )}
        <span className="text-xs text-gray-400 ml-auto">
          {filtered.length} of {sites.length}
        </span>
      </div>

      {isLoading ? (
        <div className="text-gray-400 text-sm">Loading…</div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-gray-200">
          <table className="w-full text-sm min-w-[700px]">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                <th className="px-4 py-3">ID</th>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Brand ID</th>
                <th className="px-4 py-3">Brand</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {filtered.map((s) => (
                <tr key={s.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3"><EntityIdChip id={s.id} ref={s.ref} /></td>
                  <td className="px-4 py-3 font-medium text-gray-900">
                    <Link to={`/sites/${s.id}`} className="hover:text-brand-600 transition-colors">
                      {s.name}
                    </Link>
                  </td>
                  <td className="px-4 py-3"><EntityIdChip id={s.brand_id} ref={brands.find((b) => b.id === s.brand_id)?.ref} /></td>
                  <td className="px-4 py-3 text-gray-500">{brandName(s.brand_id)}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={s.is_active ? 'active' : 'suspended'} />
                  </td>
                  <td className="px-4 py-3 flex gap-2">
                    <button onClick={() => openEdit(s)} className="text-brand-600 hover:underline text-xs">Edit</button>
                    <button
                      onClick={() => handleSessionInto(s.id)}
                      disabled={sessioningId === s.id}
                      className="text-brand-600 hover:underline text-xs disabled:opacity-50"
                    >
                      {sessioningId === s.id ? '…' : 'Session into'}
                    </button>
                    {s.is_active ? (
                      <button onClick={() => suspendMutation.mutate(s.id)} className="text-amber-600 hover:underline text-xs">Suspend</button>
                    ) : (
                      <button onClick={() => activateMutation.mutate(s.id)} className="text-green-600 hover:underline text-xs">Activate</button>
                    )}
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                  {sites.length === 0 ? 'No sites yet.' : 'No sites match the current filters.'}
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {(showCreate || editing) && (
        <Modal
          title={editing ? 'Edit Site' : 'New Site'}
          onClose={() => { setShowCreate(false); setEditing(null) }}
        >
          <form onSubmit={handleSubmit} className="space-y-4">
            {!editing && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Brand</label>
                <select
                  value={brandId}
                  onChange={(e) => setBrandId(e.target.value)}
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                >
                  {brands.map((b) => (
                    <option key={b.id} value={b.id}>{b.name}</option>
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
                placeholder="Sydney CBD"
              />
            </div>
            {!editing && (
              <>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Site email</label>
                  <input
                    type="email"
                    value={masterEmail}
                    onChange={(e) => setMasterEmail(e.target.value)}
                    required
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                    placeholder="manager@example.com"
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
            <div className="relative">
              <label className="block text-sm font-medium text-gray-700 mb-1">Street address</label>
              <input
                value={address.address_street}
                onChange={(e) => {
                  setAddress({ ...address, address_street: e.target.value })
                  setShowSuggestions(true)
                }}
                onFocus={() => setShowSuggestions(true)}
                onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
                onKeyDown={(e) => { if (e.key === 'Escape') setShowSuggestions(false) }}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                placeholder="123 George St"
                autoComplete="off"
              />
              {showSuggestions && suggestions.length > 0 && (
                <ul className="absolute z-10 mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg text-sm divide-y divide-gray-100 max-h-48 overflow-y-auto">
                  {suggestions.map((s, i) => (
                    <li
                      key={i}
                      onMouseDown={() => {
                        setAddress({ address_street: s.road, address_city: s.city, address_state: s.state, address_postcode: s.postcode })
                        setShowSuggestions(false)
                      }}
                      className="px-3 py-2 hover:bg-brand-50 cursor-pointer text-gray-700 truncate"
                      title={s.display_name}
                    >
                      {s.display_name}
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Suburb / City</label>
              <input
                value={address.address_city}
                onChange={(e) => setAddress({ ...address, address_city: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                placeholder="South Brisbane"
              />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">State</label>
                <input
                  value={address.address_state}
                  onChange={(e) => setAddress({ ...address, address_state: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                  placeholder="QLD"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Postcode</label>
                <input
                  value={address.address_postcode}
                  onChange={(e) => setAddress({ ...address, address_postcode: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                  placeholder="4101"
                />
              </div>
            </div>
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
