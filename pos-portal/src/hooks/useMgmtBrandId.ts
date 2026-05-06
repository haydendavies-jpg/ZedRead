/**
 * Resolves the brand_id for management API calls.
 *
 * Management JWT users have brand_id (brand-scope) or need a site→brand lookup.
 * For brand-scope users the JWT embeds brand_id directly.
 * For site-scope users we don't have brand_id in the JWT; the catalog APIs
 * accept site_id-scoped calls — we pass brand_id=undefined and let the backend
 * infer from the management JWT scope.
 *
 * Portal users must supply brand_id as a query param — they must navigate to
 * a specific brand context first.
 *
 * Returns the brand_id string to include as a query param, or null if unknown.
 */

import { useSearchParams } from 'react-router-dom'
import { useAuth, isMgmtUser, isPortalUser } from '../context/AuthContext'

export function useMgmtBrandId(): string | null {
  const { user } = useAuth()
  const [params] = useSearchParams()

  if (isMgmtUser(user)) {
    return user.brand_id ?? null
  }

  if (isPortalUser(user)) {
    return params.get('brand_id')
  }

  return null
}
