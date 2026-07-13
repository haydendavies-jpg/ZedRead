/**
 * Menu Studio — the combined catalog authoring surface.
 *
 * Table view hosts the Products / Modifiers / Categories tabs (each its own
 * existing page component); POS Layout view delegates to the existing
 * MenuBuilderPage (Stage 23) as-is — the grid-editor redesign (drag/resize,
 * multi-select, active-time scheduling) described in
 * design_handoff_menu_studio/README.md is a separate, larger follow-up and
 * out of scope for this pass.
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/axios'
import { useMgmtBrandId } from '../../hooks/useMgmtBrandId'
import { ProductsPage } from './ProductsPage'
import { ModifiersPage } from './ModifiersPage'
import { CategoriesPage } from './CategoriesPage'
import { MenuBuilderPage } from './MenuBuilderPage'
import type { Category, ModifierGroup, ProductListItem } from '../../types'

type Layout = 'table' | 'pos'
type Tab = 'products' | 'modifiers' | 'categories'

export function MenuStudioPage() {
  const brandId = useMgmtBrandId()
  const [layout, setLayout] = useState<Layout>('table')
  const [tab, setTab] = useState<Tab>('products')

  const params = brandId ? { brand_id: brandId } : {}

  const { data: products = [] } = useQuery<ProductListItem[]>({
    queryKey: ['products', brandId],
    queryFn: () => api.get('/products', { params: { ...params, limit: 200 } }).then((r) => r.data),
    enabled: !!brandId,
  })
  // Plain (non-nested) list — just for the tab count badge. The Modifiers tab
  // fetches the fully-nested /modifier-groups/detailed itself when it mounts;
  // fetching that heavier shape here too would pay its cost on every Menu
  // Studio visit regardless of which tab is open.
  const { data: modifierGroups = [] } = useQuery<ModifierGroup[]>({
    queryKey: ['modifier-groups', brandId],
    queryFn: () => api.get('/modifier-groups', { params: { ...params, limit: 200 } }).then((r) => r.data),
    enabled: !!brandId,
  })
  const { data: categories = [] } = useQuery<Category[]>({
    queryKey: ['categories', brandId],
    queryFn: () => api.get('/categories', { params: { ...params, limit: 500 } }).then((r) => r.data),
    enabled: !!brandId,
  })

  if (!brandId) {
    return <div className="flex items-center justify-center h-64 text-sm text-gray-400">No brand context available.</div>
  }

  const tabDef: { key: Tab; label: string; count: number }[] = [
    { key: 'products', label: 'Products', count: products.length },
    { key: 'modifiers', label: 'Modifiers', count: modifierGroups.length },
    { key: 'categories', label: 'Categories', count: categories.length },
  ]

  return (
    <div className="flex flex-col min-h-full" style={{ fontFamily: "'IBM Plex Sans', sans-serif" }}>
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 sm:px-6 pt-4 sm:pt-6 pb-4 border-b border-gray-200 dark:border-gray-700">
        <div className="flex flex-wrap items-center gap-4">
          <h1 className="font-serif font-bold text-[22px] text-gray-900 dark:text-gray-100 leading-tight">Menu Studio</h1>
          <div className="flex bg-gray-100 dark:bg-gray-800 rounded-lg p-1">
            <button
              onClick={() => setLayout('table')}
              className={`px-4 py-1.5 rounded-md text-sm font-semibold transition-colors ${layout === 'table' ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm' : 'text-gray-500 dark:text-gray-400'}`}
            >
              Table
            </button>
            <button
              onClick={() => setLayout('pos')}
              className={`px-4 py-1.5 rounded-md text-sm font-semibold transition-colors ${layout === 'pos' ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm' : 'text-gray-500 dark:text-gray-400'}`}
            >
              POS Layout
            </button>
          </div>
        </div>
      </div>

      {layout === 'table' && (
        <>
          <div className="flex items-center gap-2 px-4 sm:px-6 pt-4">
            {tabDef.map((t) => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-medium transition-colors ${
                  tab === t.key
                    ? 'bg-brand-50 dark:bg-brand-950/40 text-brand-700 dark:text-brand-300 font-semibold'
                    : 'text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'
                }`}
              >
                {t.label}
                <span className={`text-[11px] font-semibold rounded-full px-1.5 py-0.5 ${tab === t.key ? 'bg-brand-100 dark:bg-brand-900/60' : 'bg-gray-100 dark:bg-gray-700'}`}>
                  {t.count}
                </span>
              </button>
            ))}
          </div>
          {tab === 'products' && <ProductsPage />}
          {tab === 'modifiers' && <ModifiersPage />}
          {tab === 'categories' && <CategoriesPage />}
        </>
      )}

      {layout === 'pos' && <MenuBuilderPage />}
    </div>
  )
}
