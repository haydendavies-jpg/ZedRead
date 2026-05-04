/**
 * Configured Axios instance for all API calls.
 *
 * Request interceptor: attaches Bearer token from localStorage.
 * Response interceptor: on 401, queues concurrent requests and retries after
 * a single token refresh (prevents multiple simultaneous refresh race conditions).
 */

import axios from 'axios'
import type { AxiosRequestConfig } from 'axios'

const BASE_URL = import.meta.env.VITE_API_URL ?? '/api'

export const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
})

// ── Token helpers ──────────────────────────────────────────────────────────────

export const getAccessToken = () => localStorage.getItem('access_token')
export const getRefreshToken = () => localStorage.getItem('refresh_token')

export const setTokens = (access: string, refresh: string) => {
  localStorage.setItem('access_token', access)
  localStorage.setItem('refresh_token', refresh)
}

export const clearTokens = () => {
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
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

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original: AxiosRequestConfig & { _retry?: boolean } = error.config

    // Only attempt refresh on 401, and only once per request
    if (error.response?.status !== 401 || original._retry) {
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

      const { data } = await axios.post(`${BASE_URL}/auth/portal/refresh`, {
        refresh_token: refresh,
      })

      setTokens(data.access_token, data.refresh_token)
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
