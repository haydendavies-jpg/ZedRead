/**
 * Site detail page for portal admins — shows the editable company profile for
 * a Site, with logo/billing-email inheritance resolved client-side by walking
 * Site → Brand → Group (mirrors app/services/branding_service.py).
 */

import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/axios'
import { CompanyProfileForm, type EntityType, type InheritedInfo } from '../../components/CompanyProfileForm'
import type { Brand, Group, Site } from '../../types'

async function sessionInto(siteId: string): Promise<void> {
  const { data: grantData } = await api.get<{ grant_id: string }>('/admin/master-grant', {
    params: { site_id: siteId },
  })
  const { data: tokenData } = await api.post<{ access_token: string }>('/admin/impersonate', {
    grant_id: grantData.grant_id,
  })
  sessionStorage.setItem('imp_token', tokenData.access_token)
  window.open('/management', '_blank')
}

function resolveInherited(brand: Brand | undefined, group: Group | undefined): InheritedInfo {
  let logoUrl: string | null = null
  let logoSource: EntityType | null = null
  if (brand?.logo_url) {
    logoUrl = brand.logo_url
    logoSource = 'brand'
  } else if (group?.logo_url) {
    logoUrl = group.logo_url
    logoSource = 'group'
  }

  let billingEmail: string | null = null
  let billingEmailSource: EntityType | null = null
  if (brand?.billing_email) {
    billingEmail = brand.billing_email
    billingEmailSource = 'brand'
  } else if (group?.billing_email) {
    billingEmail = group.billing_email
    billingEmailSource = 'group'
  }

  return { logoUrl, logoSource, billingEmail, billingEmailSource }
}

export function SiteDetailPage() {
  const { siteId } = useParams<{ siteId: string }>()
  const [sessionError, setSessionError] = useState<string | null>(null)
  const [isSessioning, setIsSessioning] = useState(false)

  const { data: site, isLoading } = useQuery<Site>({
    queryKey: ['site', siteId],
    queryFn: () => api.get(`/sites/${siteId}`).then((r) => r.data),
    enabled: !!siteId,
  })

  const { data: brand } = useQuery<Brand>({
    queryKey: ['brand', site?.brand_id],
    queryFn: () => api.get(`/brands/${site!.brand_id}`).then((r) => r.data),
    enabled: !!site?.brand_id,
  })

  const { data: group } = useQuery<Group>({
    queryKey: ['group', brand?.group_id],
    queryFn: () => api.get(`/groups/${brand!.group_id}`).then((r) => r.data),
    enabled: !!brand?.group_id,
  })

  if (!siteId) return null

  const handleSessionInto = async () => {
    setSessionError(null)
    setIsSessioning(true)
    try {
      await sessionInto(siteId)
    } catch {
      setSessionError('Could not start session. Ensure the site has an active master user.')
    } finally {
      setIsSessioning(false)
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 sm:px-6 py-4 bg-white border-b border-gray-200">
        <div className="flex items-center gap-2 text-sm text-gray-500 mb-2">
          <Link to="/sites" className="hover:text-brand-600 transition-colors">
            Sites
          </Link>
          <span>/</span>
          <span className="text-gray-900 font-medium">
            {isLoading ? '…' : site?.name}
          </span>
        </div>

        {site && (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-4">
              <h1 className="text-xl font-semibold text-gray-900">{site.name}</h1>
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${site.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'}`}>
                {site.is_active ? 'active' : 'suspended'}
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

      <div className="flex-1 overflow-auto bg-gray-50 p-4 sm:p-6">
        {site && (
          <CompanyProfileForm
            entityType="site"
            entity={site}
            inherited={resolveInherited(brand, group)}
            invalidateKeys={[['site', siteId], ['sites']]}
          />
        )}
      </div>
    </div>
  )
}
