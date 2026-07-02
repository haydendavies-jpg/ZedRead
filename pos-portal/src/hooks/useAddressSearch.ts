/**
 * Address autocomplete via OpenStreetMap Nominatim.
 * Free, no API key required; rate-limited to 1 req/sec (acceptable for admin portal usage).
 */

import { useEffect, useRef, useState } from 'react'

export interface AddressSuggestion {
  display_name: string
  road: string
  state: string
  postcode: string
}

function extractParts(result: Record<string, unknown>): AddressSuggestion {
  const addr = (result['address'] as Record<string, string>) ?? {}
  const houseNumber = addr['house_number'] ?? ''
  const road = addr['road'] ?? ''
  const street = houseNumber ? `${houseNumber} ${road}` : road
  return {
    display_name: (result['display_name'] as string) ?? '',
    road: street,
    state: addr['state'] ?? '',
    postcode: addr['postcode'] ?? '',
  }
}

export function useAddressSearch(query: string): {
  suggestions: AddressSuggestion[]
  isLoading: boolean
} {
  const [suggestions, setSuggestions] = useState<AddressSuggestion[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (query.length < 5) {
      setSuggestions([])
      return
    }

    if (debounceRef.current) clearTimeout(debounceRef.current)

    debounceRef.current = setTimeout(async () => {
      setIsLoading(true)
      try {
        const params = new URLSearchParams({
          q: query,
          countrycode: 'au,nz',
          addressdetails: '1',
          format: 'json',
          limit: '5',
        })
        const resp = await fetch(
          `https://nominatim.openstreetmap.org/search?${params}`,
          { headers: { 'Accept-Language': 'en' } },
        )
        if (!resp.ok) return
        const data: Record<string, unknown>[] = await resp.json()
        setSuggestions(data.map(extractParts).filter((s) => s.road))
      } catch {
        setSuggestions([])
      } finally {
        setIsLoading(false)
      }
    }, 350)

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [query])

  return { suggestions, isLoading }
}
