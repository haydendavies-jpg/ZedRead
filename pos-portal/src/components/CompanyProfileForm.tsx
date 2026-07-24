/**
 * Editable company-profile form shared by the Group/Brand/Site detail pages
 * and the tenant-facing Company Profile page: name, timezone/currency/
 * country/tax-ID/billing-email, logo upload, and (Site only) address.
 */

import { useRef, useState } from 'react'
import { useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query'
import { api } from '../api/axios'
import type { Brand, Group, Site } from '../types'
import { CompanyProfileFields, type CompanyProfileValues } from './CompanyProfileFields'
import { confirmCurrencyChange } from '../utils/companyProfile'
import { useAddressSearch } from '../hooks/useAddressSearch'

export type EntityType = 'group' | 'brand' | 'site'
type Entity = Group | Brand | Site

export interface InheritedInfo {
  logoUrl: string | null
  logoSource: EntityType | null
  billingEmail: string | null
  billingEmailSource: EntityType | null
}

interface Props {
  entityType: EntityType
  entity: Entity
  inherited: InheritedInfo
  /** Query keys to invalidate after a successful save/logo upload (e.g. [['group', id], ['groups']]). */
  invalidateKeys: QueryKey[]
}

const BASE_PATH: Record<EntityType, string> = { group: '/groups', brand: '/brands', site: '/sites' }

export function CompanyProfileForm({ entityType, entity, inherited, invalidateKeys }: Props) {
  const qc = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const isSite = entityType === 'site'
  const siteEntity = isSite ? (entity as Site) : null

  const [name, setName] = useState(entity.name)
  const [profile, setProfile] = useState<CompanyProfileValues>({
    timezone: entity.timezone,
    currency: entity.currency,
    country: entity.country,
    tax_id_value: entity.tax_id_value ?? '',
    billing_email: entity.billing_email ?? '',
  })
  const [address, setAddress] = useState({
    address_street: siteEntity?.address_street ?? '',
    address_city: siteEntity?.address_city ?? '',
    address_state: siteEntity?.address_state ?? '',
    address_postcode: siteEntity?.address_postcode ?? '',
    phone_number: siteEntity?.phone_number ?? '',
  })
  const [formError, setFormError] = useState<string | null>(null)
  const [billingInfoMessage, setBillingInfoMessage] = useState<string | null>(null)
  const [showSuggestions, setShowSuggestions] = useState(false)
  const { suggestions } = useAddressSearch(isSite ? address.address_street : '')

  const invalidate = () => invalidateKeys.forEach((key) => qc.invalidateQueries({ queryKey: key }))

  const saveMutation = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.patch(`${BASE_PATH[entityType]}/${entity.id}`, body),
    onSuccess: () => { invalidate(); setFormError(null) },
    onError: () => { invalidate(); setFormError(`Failed to update ${entityType}.`) },
  })

  const logoMutation = useMutation({
    mutationFn: (file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      return api.post(`${BASE_PATH[entityType]}/${entity.id}/logo`, formData)
    },
    onSuccess: () => { invalidate(); setFormError(null) },
    onError: () => { invalidate(); setFormError('Failed to upload logo.') },
  })

  const billingInfoMutation = useMutation({
    mutationFn: () => api.post(`${BASE_PATH[entityType]}/${entity.id}/request-billing-info`),
    onSuccess: (res) => {
      setBillingInfoMessage(`Billing info request sent to ${res.data.sent_to} (${res.data.source_level} level).`)
    },
    onError: (e: unknown) => {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setBillingInfoMessage(detail ?? 'Failed to send billing info request.')
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)
    if (!confirmCurrencyChange(entity.currency, profile.currency, entityType)) return
    saveMutation.mutate({ name, ...profile, ...(isSite ? address : {}) })
  }

  const handleLogoChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) logoMutation.mutate(file)
    e.target.value = ''
  }

  const displayedLogo = entity.logo_url ?? inherited.logoUrl
  const logoIsInherited = !entity.logo_url && !!inherited.logoUrl
  const billingEmailIsInherited = !profile.billing_email && !!inherited.billingEmail

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 sm:p-6 max-w-2xl">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="flex items-center gap-4">
          <div className="w-16 h-16 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 flex items-center justify-center overflow-hidden shrink-0">
            {displayedLogo ? (
              <img src={displayedLogo} alt="Logo" className="w-full h-full object-cover" />
            ) : (
              <span className="text-gray-300 text-xs">No logo</span>
            )}
          </div>
          <div>
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={logoMutation.isPending}
              className="text-brand-600 hover:underline text-xs disabled:opacity-50"
            >
              {entity.logo_url ? 'Replace logo' : 'Upload logo'}
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="hidden"
              onChange={handleLogoChange}
            />
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">Recommended: 500×500px or larger, under 1MB. Optional.</p>
            {logoIsInherited && (
              <p className="text-xs text-gray-400 dark:text-gray-500">Inherited from {inherited.logoSource}.</p>
            )}
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Name</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            minLength={1}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
        </div>

        <CompanyProfileFields values={profile} onChange={setProfile} />
        {billingEmailIsInherited && (
          <p className="text-xs text-gray-400 dark:text-gray-500 -mt-2">
            Inherited from {inherited.billingEmailSource}: {inherited.billingEmail}
          </p>
        )}

        {isSite && (
          <>
            <div className="relative">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Street address</label>
              <input
                value={address.address_street}
                onChange={(e) => {
                  setAddress({ ...address, address_street: e.target.value })
                  setShowSuggestions(true)
                }}
                onFocus={() => setShowSuggestions(true)}
                onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
                onKeyDown={(e) => { if (e.key === 'Escape') setShowSuggestions(false) }}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                autoComplete="off"
              />
              {showSuggestions && suggestions.length > 0 && (
                <ul className="absolute z-10 mt-1 w-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg text-sm divide-y divide-gray-100 dark:divide-gray-800 max-h-48 overflow-y-auto">
                  {suggestions.map((s, i) => (
                    <li
                      key={i}
                      onMouseDown={() => {
                        setAddress({ ...address, address_street: s.road, address_city: s.city, address_state: s.state, address_postcode: s.postcode })
                        setShowSuggestions(false)
                      }}
                      className="px-3 py-2 hover:bg-brand-50 cursor-pointer text-gray-700 dark:text-gray-300 truncate"
                      title={s.display_name}
                    >
                      {s.display_name}
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Suburb / City</label>
              <input
                value={address.address_city}
                onChange={(e) => setAddress({ ...address, address_city: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">State</label>
                <input
                  value={address.address_state}
                  onChange={(e) => setAddress({ ...address, address_state: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Postcode</label>
                <input
                  value={address.address_postcode}
                  onChange={(e) => setAddress({ ...address, address_postcode: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Phone (optional)</label>
              <input
                value={address.phone_number}
                onChange={(e) => setAddress({ ...address, phone_number: e.target.value })}
                placeholder="(02) 5550 1234"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">Printed on receipts and dockets.</p>
            </div>
          </>
        )}

        {formError && <p className="text-sm text-red-600">{formError}</p>}

        <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
          <button
            type="button"
            onClick={() => billingInfoMutation.mutate()}
            disabled={billingInfoMutation.isPending}
            className="text-brand-600 hover:underline text-xs disabled:opacity-50"
          >
            Send billing info request
          </button>
          <button
            type="submit"
            disabled={saveMutation.isPending}
            className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
          >
            Save changes
          </button>
        </div>
        {billingInfoMessage && <p className="text-xs text-gray-500 dark:text-gray-400">{billingInfoMessage}</p>}
      </form>
    </div>
  )
}
