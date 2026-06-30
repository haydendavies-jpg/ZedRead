/**
 * Tenant-facing Company Profile page — shows the editable company profile for
 * the logged-in management user's site, brand, or group (whichever their JWT
 * scope resolves to), with the same inheritance display and currency-change
 * warning as the SuperAdmin portal's Group/Brand/Site detail pages.
 */

import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/axios'
import { useAuth, isMgmtUser } from '../../context/AuthContext'
import { CompanyProfileForm, type EntityType, type InheritedInfo } from '../../components/CompanyProfileForm'
import type { Brand, Group, Site } from '../../types'

export function CompanyProfilePage() {
  const { user } = useAuth()
  const mgmtUser = isMgmtUser(user) ? user : null

  if (!mgmtUser) {
    return (
      <div className="flex items-center justify-center h-64 text-sm text-gray-400">
        Company profile is only available to management users.
      </div>
    )
  }

  if (mgmtUser.scope === 'site' && mgmtUser.site_id) {
    return <SiteProfile siteId={mgmtUser.site_id} />
  }
  if (mgmtUser.scope === 'brand' && mgmtUser.brand_id) {
    return <BrandProfile brandId={mgmtUser.brand_id} />
  }
  if (mgmtUser.scope === 'group' && mgmtUser.group_id) {
    return <GroupProfile groupId={mgmtUser.group_id} />
  }

  return (
    <div className="flex items-center justify-center h-64 text-sm text-gray-400">
      No company profile available at your access level.
    </div>
  )
}

function GroupProfile({ groupId }: { groupId: string }) {
  const { data: group } = useQuery<Group>({
    queryKey: ['group', groupId],
    queryFn: () => api.get(`/groups/${groupId}`).then((r) => r.data),
  })

  if (!group) return <Loading />

  return (
    <Page title="Company Profile">
      <CompanyProfileForm
        entityType="group"
        entity={group}
        inherited={{ logoUrl: null, logoSource: null, billingEmail: null, billingEmailSource: null }}
        invalidateKeys={[['group', groupId]]}
      />
    </Page>
  )
}

function BrandProfile({ brandId }: { brandId: string }) {
  const { data: brand } = useQuery<Brand>({
    queryKey: ['brand', brandId],
    queryFn: () => api.get(`/brands/${brandId}`).then((r) => r.data),
  })
  const { data: group } = useQuery<Group>({
    queryKey: ['group', brand?.group_id],
    queryFn: () => api.get(`/groups/${brand!.group_id}`).then((r) => r.data),
    enabled: !!brand?.group_id,
  })

  if (!brand) return <Loading />

  return (
    <Page title="Company Profile">
      <CompanyProfileForm
        entityType="brand"
        entity={brand}
        inherited={{
          logoUrl: group?.logo_url ?? null,
          logoSource: group?.logo_url ? 'group' : null,
          billingEmail: group?.billing_email ?? null,
          billingEmailSource: group?.billing_email ? 'group' : null,
        }}
        invalidateKeys={[['brand', brandId]]}
      />
    </Page>
  )
}

function SiteProfile({ siteId }: { siteId: string }) {
  const { data: site } = useQuery<Site>({
    queryKey: ['site', siteId],
    queryFn: () => api.get(`/sites/${siteId}`).then((r) => r.data),
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

  if (!site) return <Loading />

  const inherited = resolveSiteInherited(brand, group)

  return (
    <Page title="Company Profile">
      <CompanyProfileForm entityType="site" entity={site} inherited={inherited} invalidateKeys={[['site', siteId]]} />
    </Page>
  )
}

function resolveSiteInherited(brand: Brand | undefined, group: Group | undefined): InheritedInfo {
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

function Page({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="p-4 sm:p-6">
      <h1 className="text-xl font-semibold text-gray-900 mb-4">{title}</h1>
      {children}
    </div>
  )
}

function Loading() {
  return <div className="p-4 sm:p-6 text-gray-400 text-sm">Loading…</div>
}
