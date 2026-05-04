/** Shared TypeScript types for the ZedRead portal API. */

export interface Group {
  id: string
  name: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface Brand {
  id: string
  group_id: string
  name: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface Site {
  id: string
  brand_id: string
  name: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface License {
  id: string
  site_id: string
  plan_name: string
  status: 'active' | 'expired' | 'disabled'
  monthly_fee_cents: number
  is_trial: boolean
  starts_at: string
  expires_at: string
  created_at: string
  updated_at: string
}

export interface LicenseInvoice {
  id: string
  license_id: string
  amount_cents: number
  status: 'open' | 'paid' | 'cancelled'
  period_start: string
  period_end: string
  paid_at: string | null
  created_at: string
}

export interface PortalUser {
  id: string
  email: string
  name: string
  role: 'super_admin' | 'admin' | 'reseller'
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface AuthTokens {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface PaginationParams {
  skip?: number
  limit?: number
}
