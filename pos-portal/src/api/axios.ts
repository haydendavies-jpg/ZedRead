/**
 * Configured Axios instance for all API calls.
 *
 * Request interceptor: attaches Bearer token from localStorage.
 * Response interceptor: on 401, queues concurrent requests and retries after
 * a single token refresh (prevents multiple simultaneous refresh race conditions).
 *
 * Token-type awareness: management JWTs use /auth/portal/mgmt-refresh;
 * portal JWTs use /auth/portal/refresh. The token type is stored alongside
 * tokens so the interceptor can pick the right endpoint.
 */

import axios from 'axios'
import type { AxiosRequestConfig } from 'axios'
import type { TokenType } from '../types'

const BASE_URL = import.meta.env.VITE_API_URL ?? '/api'

export const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
})

// ── Token helpers ──────────────────────────────────────────────────────────────

/**
 * Impersonated ("Session into") management sessions are scoped to a single tab
 * via sessionStorage. They must NEVER be written to localStorage: localStorage
 * is shared across tabs, so storing the impersonation token there would hijack
 * the admin's own session in every other open tab.
 */
const IMP_SESSION_KEY = 'imp_access_token'

/** True when this tab is running an admin-impersonated management session. */
export const isImpersonationSession = () => sessionStorage.getItem(IMP_SESSION_KEY) !== null

/** Store the impersonation token for this tab only. */
export const setImpersonationSession = (token: string) =>
  sessionStorage.setItem(IMP_SESSION_KEY, token)

export const getAccessToken = () =>
  sessionStorage.getItem(IMP_SESSION_KEY) ?? localStorage.getItem('access_token')

// Impersonation tokens are short-lived and have no refresh token; returning
// null prevents the 401 interceptor from refreshing with the admin's portal
// refresh token, which would swap a portal token into a management tab.
export const getRefreshToken = () =>
  isImpersonationSession() ? null : localStorage.getItem('refresh_token')

export const getTokenType = (): TokenType | null =>
  isImpersonationSession() ? 'mgmt_access' : (localStorage.getItem('token_type') as TokenType | null)

export const setTokens = (access: string, refresh: string, tokenType: TokenType) => {
  localStorage.setItem('access_token', access)
  localStorage.setItem('refresh_token', refresh)
  localStorage.setItem('token_type', tokenType)
}

export const clearTokens = () => {
  // In an impersonated tab, end only this tab's session — the admin's real
  // tokens in localStorage belong to their other tab(s) and must survive.
  if (isImpersonationSession()) {
    sessionStorage.removeItem(IMP_SESSION_KEY)
    return
  }
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
  localStorage.removeItem('token_type')
}

// ── Request interceptor — attach access token ──────────────────────────────────

api.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// ── Response interceptor — transparent token refresh ──────────────────────────

/** True while a refresh call is in flight. */
let isRefreshing = false

/**
 * Queue of resolve/reject callbacks for requests that arrived while a refresh
 * was already in progress. Drained once the refresh completes.
 */
let pendingQueue: Array<{ resolve: (token: string) => void; reject: (err: unknown) => void }> = []

const drainQueue = (token: string | null, error: unknown) => {
  pendingQueue.forEach(({ resolve, reject }) => {
    if (token) resolve(token)
    else reject(error)
  })
  pendingQueue = []
}

/** Pick the correct refresh endpoint based on the stored token type. */
const refreshEndpoint = (): string => {
  const t = getTokenType()
  return t === 'mgmt_access'
    ? `${BASE_URL}/auth/portal/mgmt-refresh`
    : `${BASE_URL}/auth/portal/refresh`
}

/** Field name for the refresh token body — matches both refresh schemas. */
const refreshBody = () => ({ refresh_token: getRefreshToken() })

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original: AxiosRequestConfig & { _retry?: boolean } = error.config

    // Only attempt refresh on 401, and only once per request
    if (error.response?.status !== 401 || original._retry) {
      return Promise.reject(error)
    }

    // No refresh token stored — we're not authenticated yet (e.g. login page).
    // Pass the original error through so the caller can read response.data.detail.
    if (!getRefreshToken()) {
      return Promise.reject(error)
    }

    original._retry = true

    if (isRefreshing) {
      // Another refresh is already in flight — queue this request
      return new Promise((resolve, reject) => {
        pendingQueue.push({
          resolve: (token) => {
            if (original.headers) original.headers.Authorization = `Bearer ${token}`
            resolve(api(original))
          },
          reject,
        })
      })
    }

    isRefreshing = true

    try {
      const refresh = getRefreshToken()
      if (!refresh) throw new Error('No refresh token')

      const tokenType = getTokenType() ?? 'portal_access'
      const { data } = await axios.post(refreshEndpoint(), refreshBody())

      setTokens(data.access_token, data.refresh_token, tokenType)
      drainQueue(data.access_token, null)

      if (original.headers) original.headers.Authorization = `Bearer ${data.access_token}`
      return api(original)
    } catch (refreshError) {
      drainQueue(null, refreshError)
      clearTokens()
      window.location.href = '/login'
      return Promise.reject(refreshError)
    } finally {
      isRefreshing = false
    }
  }
)
