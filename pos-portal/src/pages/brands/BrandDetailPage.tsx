/**
 * Brand detail page for portal admins — shows brand info with inline
 * catalog management tabs (Products, Categories, Tax, Reports, Users).
 *
 * Uses BrandContext.Provider so embedded management pages receive the
 * brand_id without needing URL search params or JWT scope.
 */

import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/axios'
import { BrandContext } from '../../context/BrandContext'
import { CompanyProfileForm } from '../../components/CompanyProfileForm'
import { ProductsPage } from '../management/ProductsPage'
import { CategoriesPage } from '../management/CategoriesPage'
import { TaxPage } from '../management/TaxPage'
import { ReportsPage } from '../management/ReportsPage'
import { UsersPage } from '../management/UsersPage'
import { SiteOverridesPage } from '../management/SiteOverridesPage'
import { sessionInto } from '../../utils/impersonation'
import type { Brand, Group } from '../../types'

type Tab = 'overview' | 'products' | 'categories' | 'tax' | 'overrides' | 'reports' | 'users'

const TABS: { id: Tab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'products', label: 'Products' },
  { id: 'categories', label: 'Categories' },
  { id: 'tax', label: 'Tax' },
  { id: 'overrides', label: 'Site Overrides' },
  { id: 'reports', label: 'Reports' },
  { id: 'users', label: 'Users & Grants' },
]

export function BrandDetailPage() {
  const { brandId } = useParams<{ brandId: string }>()
  const [activeTab, setActiveTab] = useState<Tab>('overview')
  const [sessionError, setSessionError] = useState<string | null>(null)
  const [isSessioning, setIsSessioning] = useState(false)

  const { data: brand, isLoading } = useQuery<Brand>({
    queryKey: ['brand', brandId],
    queryFn: () => api.get(`/brands/${brandId}`).then((r) => r.data),
    enabled: !!brandId,
  })

  if (!brandId) return null

  const handleSessionInto = async () => {
    setSessionError(null)
    setIsSessioning(true)
    try {
      await sessionInto('brand', brandId)
    } catch {
      setSessionError('Could not start session. Ensure the brand has an active master user.')
    } finally {
      setIsSessioning(false)
    }
  }

  return (
    <BrandContext.Provider value={brandId}>
      <div className="flex flex-col h-full">
        {/* Header */}
        <div className="px-4 sm:px-6 py-4 bg-white border-b border-gray-200">
          <div className="flex items-center gap-2 text-sm text-gray-500 mb-2">
            <Link to="/brands" className="hover:text-brand-600 transition-colors">
              Brands
            </Link>
            <span>/</span>
            <span className="text-gray-900 font-medium">
              {isLoading ? '…' : brand?.name}
            </span>
          </div>

          {brand && (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-4">
                <h1 className="text-xl font-semibold text-gray-900">{brand.name}</h1>
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${brand.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'}`}>
                  {brand.is_active ? 'active' : 'suspended'}
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

        {/* Tab bar */}
        <div className="flex gap-0 px-4 sm:px-6 bg-white border-b border-gray-200 overflow-x-auto">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
                activeTab === tab.id
                  ? 'border-brand-600 text-brand-600'
                  : 'border-transparent text-gray-500 hover:text-gray-900'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="flex-1 overflow-auto bg-gray-50">
          {activeTab === 'overview' && brand && <BrandOverview brand={brand} />}
          {activeTab === 'products' && <ProductsPage />}
          {activeTab === 'categories' && <CategoriesPage />}
          {activeTab === 'tax' && <TaxPage />}
          {activeTab === 'overrides' && <SiteOverridesPage />}
          {activeTab === 'reports' && <ReportsPage />}
          {activeTab === 'users' && <UsersPage />}
        </div>
      </div>
    </BrandContext.Provider>
  )
}

function BrandOverview({ brand }: { brand: Brand }) {
  const { data: group } = useQuery<Group>({
    queryKey: ['group', brand.group_id],
    queryFn: () => api.get(`/groups/${brand.group_id}`).then((r) => r.data),
    enabled: !!brand.group_id,
  })

  return (
    <div className="p-4 sm:p-6">
      <CompanyProfileForm
        entityType="brand"
        entity={brand}
        inherited={{
          logoUrl: group?.logo_url ?? null,
          logoSource: group?.logo_url ? 'group' : null,
          billingEmail: group?.billing_email ?? null,
          billingEmailSource: group?.billing_email ? 'group' : null,
        }}
        invalidateKeys={[['brand', brand.id], ['brands']]}
      />

      <p className="mt-4 text-sm text-gray-400 max-w-2xl">
        Use the tabs above to manage this brand's catalog, tax settings, reports, and user access.
      </p>
    </div>
  )
}
