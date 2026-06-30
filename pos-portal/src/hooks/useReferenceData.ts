/**
 * Read-only reference data backing the company-profile dropdowns
 * (timezone/currency/country selects and the country-driven tax ID label).
 *
 * Fetched once per session and cached indefinitely — this data only
 * changes with a backend deploy, never at runtime.
 */

import { useQuery } from '@tanstack/react-query'
import { api } from '../api/axios'
import type { CodeName } from '../types'

const STALE_TIME = Infinity

async function fetchTimezones(): Promise<string[]> {
  const { data } = await api.get('/reference/timezones')
  return data
}

async function fetchCountries(): Promise<CodeName[]> {
  const { data } = await api.get('/reference/countries')
  return data
}

async function fetchCurrencies(): Promise<CodeName[]> {
  const { data } = await api.get('/reference/currencies')
  return data
}

export function useTimezones() {
  return useQuery({ queryKey: ['reference', 'timezones'], queryFn: fetchTimezones, staleTime: STALE_TIME })
}

export function useCountries() {
  return useQuery({ queryKey: ['reference', 'countries'], queryFn: fetchCountries, staleTime: STALE_TIME })
}

export function useCurrencies() {
  return useQuery({ queryKey: ['reference', 'currencies'], queryFn: fetchCurrencies, staleTime: STALE_TIME })
}

/** Resolves the tax-ID field label for a given country code; null while no country is selected. */
export function useTaxIdLabel(country: string | null) {
  return useQuery({
    queryKey: ['reference', 'tax-id-label', country],
    queryFn: async () => {
      const { data } = await api.get('/reference/tax-id-label', { params: { country } })
      return data.label as string
    },
    enabled: !!country && country.length === 2,
    staleTime: STALE_TIME,
  })
}
