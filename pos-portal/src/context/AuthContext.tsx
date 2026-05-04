/**
 * Authentication context — provides current user, login, and logout to the tree.
 *
 * Access token is decoded client-side (no extra round-trip) to read role/id.
 * The refresh interceptor in axios.ts handles silent token renewal.
 */

import React, { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, clearTokens, getAccessToken, setTokens } from '../api/axios'
import type { PortalUser } from '../types'

interface AuthContextValue {
  user: PortalUser | null
  isLoading: boolean
  login: (email: string, password: string) => Promise<void>
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

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<PortalUser | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  /** Fetch the current user from the API using the stored token. */
  const fetchCurrentUser = useCallback(async () => {
    const token = getAccessToken()
    if (!token) {
      setIsLoading(false)
      return
    }
    try {
      const payload = decodePayload(token)
      const id = payload['sub'] as string
      const { data } = await api.get<PortalUser>(`/portal-users/${id}`)
      setUser(data)
    } catch {
      clearTokens()
      setUser(null)
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchCurrentUser()
  }, [fetchCurrentUser])

  const login = useCallback(async (email: string, password: string) => {
    const { data } = await api.post('/auth/portal/login', { email, password })
    setTokens(data.access_token, data.refresh_token)
    await fetchCurrentUser()
  }, [fetchCurrentUser])

  const logout = useCallback(async () => {
    try {
      await api.post('/auth/portal/logout')
    } finally {
      clearTokens()
      setUser(null)
    }
  }, [])

  return (
    <AuthContext.Provider value={{ user, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
