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
import { ProductsPage } from '../management/ProductsPage'
import { CategoriesPage } from '../management/CategoriesPage'
import { TaxPage } from '../management/TaxPage'
import { ReportsPage } from '../management/ReportsPage'
import { UsersPage } from '../management/UsersPage'
import { SiteOverridesPage } from '../management/SiteOverridesPage'
import type { Brand } from '../../types'

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

  const { data: brand, isLoading } = useQuery<Brand>({
    queryKey: ['brand', brandId],
    queryFn: () => api.get(`/brands/${brandId}`).then((r) => r.data),
    enabled: !!brandId,
  })

  if (!brandId) return null

  return (
    <BrandContext.Provider value={brandId}>
      <div className="flex flex-col h-full">
        {/* Header */}
        <div className="px-6 py-4 bg-white border-b border-gray-200">
          <div className="flex items-center gap-2 text-sm text-gray-500 mb-2">
            <Link to="/brands" className="hover:text-indigo-600 transition-colors">
              Brands
            </Link>
            <span>/</span>
            <span className="text-gray-900 font-medium">
              {isLoading ? '…' : brand?.name}
            </span>
          </div>

          {brand && (
            <div className="flex items-center gap-4">
              <h1 className="text-xl font-semibold text-gray-900">{brand.name}</h1>
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${brand.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'}`}>
                {brand.is_active ? 'active' : 'suspended'}
              </span>
            </div>
          )}
        </div>

        {/* Tab bar */}
        <div className="flex gap-0 px-6 bg-white border-b border-gray-200 overflow-x-auto">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
                activeTab === tab.id
                  ? 'border-indigo-600 text-indigo-600'
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
  return (
    <div className="p-6 max-w-lg">
      <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-3">
        <div className="flex justify-between text-sm">
          <span className="text-gray-500">Brand ID</span>
          <span className="font-mono text-gray-700 text-xs">{brand.id}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-500">Group ID</span>
          <span className="font-mono text-gray-700 text-xs">{brand.group_id}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-500">Name</span>
          <span className="text-gray-900 font-medium">{brand.name}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-500">Created</span>
          <span className="text-gray-700">{new Date(brand.created_at).toLocaleDateString()}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-500">Status</span>
          <span className={brand.is_active ? 'text-green-600' : 'text-gray-500'}>
            {brand.is_active ? 'Active' : 'Suspended'}
          </span>
        </div>
      </div>

      <p className="mt-4 text-sm text-gray-400">
        Use the tabs above to manage this brand's catalog, tax settings, reports, and user access.
      </p>
    </div>
  )
}
