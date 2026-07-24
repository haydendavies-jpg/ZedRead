/**
 * Printing — Printer Locations + Printer Templates tabs.
 *
 * Same tab-shell pattern as MenuStudioPage.tsx: a segmented control switches
 * between the two sub-pages, each fetching its own data.
 */

import { useState } from 'react'
import { PrinterLocationsPage } from './PrinterLocationsPage'
import { PrintTemplatesPage } from './PrintTemplatesPage'

type Tab = 'locations' | 'templates'

export function PrintingPage() {
  const [tab, setTab] = useState<Tab>('locations')

  return (
    <div className="flex flex-col min-h-full" style={{ fontFamily: "'IBM Plex Sans', sans-serif" }}>
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 sm:px-6 pt-4 sm:pt-6 pb-4 border-b border-gray-200 dark:border-gray-700">
        <div className="flex flex-wrap items-center gap-4">
          <h1 className="font-serif font-bold text-[22px] text-gray-900 dark:text-gray-100 leading-tight">Printing</h1>
          <div className="flex bg-gray-100 dark:bg-gray-800 rounded-lg p-1">
            <button
              onClick={() => setTab('locations')}
              className={`px-4 py-1.5 rounded-md text-sm font-semibold transition-colors ${tab === 'locations' ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm' : 'text-gray-500 dark:text-gray-400'}`}
            >
              Printer Locations
            </button>
            <button
              onClick={() => setTab('templates')}
              className={`px-4 py-1.5 rounded-md text-sm font-semibold transition-colors ${tab === 'templates' ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm' : 'text-gray-500 dark:text-gray-400'}`}
            >
              Printer Templates
            </button>
          </div>
        </div>
      </div>

      {tab === 'locations' && <PrinterLocationsPage />}
      {tab === 'templates' && <PrintTemplatesPage />}
    </div>
  )
}
