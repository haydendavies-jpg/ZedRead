/**
 * Admin "Session into" helper — starts an impersonated management-portal
 * session for a group/brand/site in a NEW tab, without touching the admin's
 * own session in the current tab.
 *
 * Handoff mechanism: the impersonation JWT is placed in sessionStorage under
 * 'imp_token'; window.open() copies the opener's sessionStorage into the new
 * tab, where AuthContext.restoreSession picks it up. The key is removed from
 * THIS tab immediately after the copy so a later refresh of the admin tab
 * cannot accidentally turn it into the impersonated session.
 */

import { api } from '../api/axios'

export type ImpersonationScope = 'group' | 'brand' | 'site'

/** Look up the entity's master-user grant, mint an impersonation token, and open /management in a new tab. */
export async function sessionInto(scope: ImpersonationScope, entityId: string): Promise<void> {
  const { data: grantData } = await api.get<{ grant_id: string }>('/admin/master-grant', {
    params: { [`${scope}_id`]: entityId },
  })
  const { data: tokenData } = await api.post<{ access_token: string }>('/admin/impersonate', {
    grant_id: grantData.grant_id,
  })
  sessionStorage.setItem('imp_token', tokenData.access_token)
  window.open('/management', '_blank')
  // The new tab has already received a copy of sessionStorage — remove the
  // token here so this admin tab never adopts the impersonated session.
  sessionStorage.removeItem('imp_token')
}
