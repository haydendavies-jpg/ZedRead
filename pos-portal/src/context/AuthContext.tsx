/**
 * Authentication context — provides current user, login, and logout to the tree.
 *
 * Supports two user types:
 *   portal_access — PortalUser (super_admin, admin, reseller); fetched from API.
 *   mgmt_access   — MgmtUser (POS manager with portal access); decoded from JWT.
 *
 * When login returns available_grants (multi-grant POS user), the context exposes
 * pendingGrants + selectGrant so the login page can render a scope selector.
 */

import React, { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, clearTokens, getAccessToken, getTokenType, setTokens } from '../api/axios'
import type { GrantSummary, MgmtTokenPayload, MgmtUser, PortalUser, TokenType, UnifiedLoginResponse } from '../types'

export type AuthUser = PortalUser | MgmtUser

interface AuthContextValue {
  user: AuthUser | null
  tokenType: TokenType | null
  isLoading: boolean
  /** Non-null when POS user logged in with multiple grants; cleared after selectGrant(). */
  pendingGrants: GrantSummary[] | null
  pendingUserId: string | null
  login: (email: string, password: string) => Promise<void>
  /** Call after the user picks a grant from pendingGrants. Completes the login. */
  selectGrant: (grantId: string, password: string) => Promise<void>
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
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [tokenType, setTokenType] = useState<TokenType | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [pendingGrants, setPendingGrants] = useState<GrantSummary[] | null>(null)
  const [pendingUserId, setPendingUserId] = useState<string | null>(null)

  /** Restore session from a stored access token. */
  const restoreSession = useCallback(async () => {
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
        const { data } = await api.get<PortalUser>(`/portal-users/${id}`)
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

  const login = useCallback(async (email: string, password: string) => {
    const { data } = await api.post<UnifiedLoginResponse>('/auth/portal/login', { email, password })

    if (data.access_token && data.refresh_token) {
      // Direct login — either portal user or single-grant POS user
      const payload = decodePayload(data.access_token)
      const type = (payload['type'] as TokenType) ?? 'portal_access'
      setTokens(data.access_token, data.refresh_token, type)

      if (type === 'mgmt_access') {
        setUser(mgmtUserFromPayload(payload))
        setTokenType('mgmt_access')
      } else {
        const id = payload['sub'] as string
        const { data: portalUser } = await api.get<PortalUser>(`/portal-users/${id}`)
        setUser(portalUser)
        setTokenType('portal_access')
      }
    } else if (data.available_grants && data.user_id) {
      // Multi-grant POS user — need scope selection before completing login
      setPendingGrants(data.available_grants)
      setPendingUserId(data.user_id)
    }
  }, [])

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
    }
  }, [])

  return (
    <AuthContext.Provider value={{ user, tokenType, isLoading, pendingGrants, pendingUserId, login, selectGrant, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}

/** True if the logged-in user is a portal admin (super_admin, admin, reseller). */
export function isPortalUser(user: AuthUser | null): user is PortalUser {
  return user !== null && 'role' in user
}

/** True if the logged-in user is a management JWT holder. */
export function isMgmtUser(user: AuthUser | null): user is MgmtUser {
  return user !== null && 'tokenType' in user && (user as MgmtUser).tokenType === 'mgmt_access'
}
