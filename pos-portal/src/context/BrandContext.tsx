/**
 * BrandContext — provides a brand_id override when a portal admin is viewing
 * a specific brand's detail page. Management pages read this via useMgmtBrandId
 * so they don't need to know whether they're embedded in a detail view or not.
 */

import { createContext, useContext } from 'react'

export const BrandContext = createContext<string | null>(null)

/** Returns the brand_id injected by BrandDetailPage, or null if not inside one. */
export function useBrandContext(): string | null {
  return useContext(BrandContext)
}
