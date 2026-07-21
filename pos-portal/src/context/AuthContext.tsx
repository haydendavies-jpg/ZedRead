/**
 * Authentication context — provides current user, login, and logout to the tree.
 *
 * Supports two user types:
 *   portal_access — User with superadmin_role set; fetched from API.
 *   mgmt_access   — MgmtUser (POS manager with portal access); decoded from JWT.
 *
 * When login returns available_grants (multi-grant POS user), the context exposes
 * pendingGrants + selectGrant so the login page can render a scope selector.
 */

import React, { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, clearTokens, getAccessToken, getTokenType, setImpersonationSession, setTokens } from '../api/axios'
import type { GrantSummary, IdentitySummary, MgmtTokenPayload, MgmtUser, User, TokenType, UnifiedLoginResponse } from '../types'

export type AuthUser = User | MgmtUser

interface AuthContextValue {
  user: AuthUser | null
  tokenType: TokenType | null
  isLoading: boolean
  /** True when the current management session was initiated by an admin impersonation. */
  isImpersonated: boolean
  /** Display name of the impersonating admin when isImpersonated is true. */
  impersonatorName: string | null
  /** Non-null when POS user logged in with multiple grants; cleared after selectGrant(). */
  pendingGrants: GrantSummary[] | null
  pendingUserId: string | null
  /**
   * Non-null when a matching row (or rows) offered more than one login capability
   * (ROLE_MODEL.md §3); cleared after selectIdentity().
   */
  pendingIdentities: IdentitySummary[] | null
  /**
   * Attempt login. Returns 'direct' when tokens were issued immediately (portal
   * user or single-grant POS user) so the caller can navigate away. Returns
   * 'grant_selection' when the POS user has multiple grants and must pick one
   * via selectGrant(). Returns 'identity_selection' when the email matches both
   * more than one capability and the caller must pick one via
   * selectIdentity(). In the two selection cases the caller should NOT navigate —
   * LoginPage re-renders with the appropriate selector automatically.
   */
  login: (email: string, password: string) => Promise<'direct' | 'grant_selection' | 'identity_selection'>
  /** Call after the user picks a grant from pendingGrants. Completes the login. */
  selectGrant: (grantId: string, password: string) => Promise<void>
  /**
   * Call after the user picks an identity from pendingIdentities. Re-verifies
   * credentials for the chosen identity and issues tokens directly, or surfaces
   * a follow-up grant selection when the chosen User has multiple grants.
   */
  selectIdentity: (identityType: 'superadmin' | 'user', email: string, password: string) => Promise<'direct' | 'grant_selection'>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

/** Decode the JWT payload (no signature verification — server handles that). */
function decodePayload(token: string): Record<string, unknown> {
  try {
    return JSON.parse(atob(token.split('.')[1]))
  } catch {
    return {}
  }
}

/** Build a MgmtUser from a management JWT payload. */
function mgmtUserFromPayload(payload: Record<string, unknown>): MgmtUser {
  const p = payload as unknown as MgmtTokenPayload
  return {
    id: p.sub,
    name: (payload['name'] as string) ?? 'Manager',
    email: (payload['email'] as string) ?? '',
    tokenType: 'mgmt_access',
    scope: p.scope,
    grant_id: p.grant_id,
    site_id: p.site_id,
    brand_id: p.brand_id,
    group_id: p.group_id,
    imp_id: p.imp_id,
    imp_email: p.imp_email,
    imp_name: p.imp_name,
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [tokenType, setTokenType] = useState<TokenType | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [pendingGrants, setPendingGrants] = useState<GrantSummary[] | null>(null)
  const [pendingUserId, setPendingUserId] = useState<string | null>(null)
  const [pendingIdentities, setPendingIdentities] = useState<IdentitySummary[] | null>(null)

  /**
   * Apply an issued token pair to the session, resolving the user from the
   * token type. Shared by the direct-login and identity-selection paths.
   */
  const applyTokens = useCallback(async (accessToken: string, refreshToken: string) => {
    const payload = decodePayload(accessToken)
    const type = (payload['type'] as TokenType) ?? 'portal_access'
    setTokens(accessToken, refreshToken, type)

    if (type === 'mgmt_access') {
      setUser(mgmtUserFromPayload(payload))
      setTokenType('mgmt_access')
    } else {
      const id = payload['sub'] as string
      const { data: portalAdmin } = await api.get<User>(`/users/${id}`)
      setUser(portalAdmin)
      setTokenType('portal_access')
    }
  }, [])

  /** Restore session from a stored access token, or from an impersonation token in sessionStorage. */
  const restoreSession = useCallback(async () => {
    // Admin impersonation: token placed in sessionStorage by the admin portal.
    // Store it per-tab ONLY (never via setTokens/localStorage — that would
    // overwrite the admin's own session in every other open tab).
    const impToken = sessionStorage.getItem('imp_token')
    if (impToken) {
      sessionStorage.removeItem('imp_token')
      try {
        const payload = decodePayload(impToken)
        setImpersonationSession(impToken)
        setUser(mgmtUserFromPayload(payload))
        setTokenType('mgmt_access')
      } catch {
        // Malformed token — fall through to normal session restore
      } finally {
        setIsLoading(false)
        return
      }
    }

    const token = getAccessToken()
    const storedType = getTokenType()
    if (!token || !storedType) {
      setIsLoading(false)
      return
    }

    try {
      const payload = decodePayload(token)

      if (storedType === 'mgmt_access') {
        setUser(mgmtUserFromPayload(payload))
        setTokenType('mgmt_access')
      } else {
        const id = payload['sub'] as string
        const { data } = await api.get<User>(`/users/${id}`)
        setUser(data)
        setTokenType('portal_access')
      }
    } catch {
      clearTokens()
      setUser(null)
      setTokenType(null)
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    restoreSession()
  }, [restoreSession])

  const login = useCallback(async (email: string, password: string): Promise<'direct' | 'grant_selection' | 'identity_selection'> => {
    const { data } = await api.post<UnifiedLoginResponse>('/auth/portal/login', { email, password })

    if (data.access_token && data.refresh_token) {
      // Direct login — either portal user or single-grant POS user
      await applyTokens(data.access_token, data.refresh_token)
      return 'direct'
    } else if (data.available_identities && data.available_identities.length > 0) {
      // A matching row (or rows) offered more than one capability — pick which
      // to enter before any token is issued (ROLE_MODEL.md §3).
      setPendingIdentities(data.available_identities)
      return 'identity_selection'
    } else if (data.available_grants && data.user_id) {
      // Multi-grant POS user — need scope selection before completing login
      setPendingGrants(data.available_grants)
      setPendingUserId(data.user_id)
      return 'grant_selection'
    }
    // Fallback — should not be reached with a well-formed API response
    return 'grant_selection'
  }, [applyTokens])

  /**
   * Complete login after the user picks an identity from pendingIdentities.
   * Re-verifies credentials for the chosen identity_type via /identity-token.
   */
  const selectIdentity = useCallback(
    async (identityType: 'superadmin' | 'user', email: string, password: string): Promise<'direct' | 'grant_selection'> => {
      const { data } = await api.post<UnifiedLoginResponse>(
        '/auth/portal/identity-token',
        { email, password, identity_type: identityType },
      )

      if (data.access_token && data.refresh_token) {
        // Identity resolved to a single token (superadmin, or single-grant user)
        await applyTokens(data.access_token, data.refresh_token)
        setPendingIdentities(null)
        return 'direct'
      }
      if (data.available_grants && data.user_id) {
        // Chosen User identity has multiple grants — fall through to scope selection
        setPendingGrants(data.available_grants)
        setPendingUserId(data.user_id)
        setPendingIdentities(null)
        return 'grant_selection'
      }
      // Fallback — should not be reached with a well-formed API response
      return 'grant_selection'
    },
    [applyTokens],
  )

  /** Complete login after the user selects a grant from the scope selector. */
  const selectGrant = useCallback(async (grantId: string, password: string) => {
    if (!pendingUserId) throw new Error('No pending login')

    const { data } = await api.post<{ access_token: string; refresh_token: string }>(
      '/auth/portal/management-token',
      { user_id: pendingUserId, grant_id: grantId, password },
    )

    const payload = decodePayload(data.access_token)
    setTokens(data.access_token, data.refresh_token, 'mgmt_access')
    setUser(mgmtUserFromPayload(payload))
    setTokenType('mgmt_access')
    setPendingGrants(null)
    setPendingUserId(null)
  }, [pendingUserId])

  const logout = useCallback(async () => {
    try {
      await api.post('/auth/portal/logout')
    } finally {
      clearTokens()
      setUser(null)
      setTokenType(null)
      setPendingGrants(null)
      setPendingUserId(null)
      setPendingIdentities(null)
    }
  }, [])

  const mgmtUser = isMgmtUser(user) ? user : null
  const isImpersonated = !!mgmtUser?.imp_id
  const impersonatorName = mgmtUser?.imp_name ?? null

  return (
    <AuthContext.Provider value={{ user, tokenType, isLoading, isImpersonated, impersonatorName, pendingGrants, pendingUserId, pendingIdentities, login, selectGrant, selectIdentity, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}

/** True if the logged-in user is a portal admin (superadmin_role set: admin, reseller_staff). */
export function isSuperAdmin(user: AuthUser | null): user is User {
  return user !== null && 'superadmin_role' in user
}

/** True if the logged-in user is a management JWT holder. */
export function isMgmtUser(user: AuthUser | null): user is MgmtUser {
  return user !== null && 'tokenType' in user && (user as MgmtUser).tokenType === 'mgmt_access'
}
