/**
 * Resolves the brand_id for management API calls.
 *
 * Priority order:
 * 1. BrandContext — set when embedded inside a BrandDetailPage (portal admin drill-down).
 * 2. Management JWT — brand_id from the token for brand-scope management users.
 * 3. URL search param brand_id — for SuperAdmin users navigating with ?brand_id=xxx.
 * 4. null — site-scope management users (API resolves brand from their grant).
 *
 * Returns the brand_id string to include as a query param, or null if unknown.
 */

import { useSearchParams } from 'react-router-dom'
import { useAuth, isMgmtUser, isSuperAdmin } from '../context/AuthContext'
import { useBrandContext } from '../context/BrandContext'

export function useMgmtBrandId(): string | null {
  const { user } = useAuth()
  const [params] = useSearchParams()
  const brandCtx = useBrandContext()

  // SuperAdmin drill-down — brand is injected by BrandDetailPage
  if (brandCtx) return brandCtx

  if (isMgmtUser(user)) {
    return user.brand_id ?? null
  }

  if (isSuperAdmin(user)) {
    return params.get('brand_id')
  }

  return null
}
