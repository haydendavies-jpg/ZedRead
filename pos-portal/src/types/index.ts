/** Shared TypeScript types for the ZedRead portal API. */

// ── Auth types ────────────────────────────────────────────────────────────────

export type TokenType = 'portal_access' | 'mgmt_access'

export interface GrantSummary {
  grant_id: string
  scope: 'site' | 'brand' | 'group'
  scope_name: string
  access_profile_name: string
}

/** Response from POST /auth/portal/login — superset of the old TokenResponse. */
export interface UnifiedLoginResponse {
  token_type: string
  /** Set when login resolved to a single token (portal user or single-grant POS user). */
  access_token?: string
  refresh_token?: string
  user_id?: string
  user_name?: string
  /** Set instead of access_token when POS user has multiple portal-capable grants. */
  available_grants?: GrantSummary[]
}

export interface ManagementTokenRequest {
  user_id: string
  grant_id: string
  password: string
}

/** Decoded management JWT payload. */
export interface MgmtTokenPayload {
  sub: string
  type: 'mgmt_access'
  scope: 'site' | 'brand' | 'group'
  grant_id: string
  site_id?: string
  brand_id?: string
  group_id?: string
  name?: string
  email?: string
}

/** Auth-context user for a management JWT holder. */
export interface MgmtUser {
  id: string
  name: string
  email: string
  tokenType: 'mgmt_access'
  scope: 'site' | 'brand' | 'group'
  grant_id: string
  site_id?: string
  brand_id?: string
  group_id?: string
}

// ── Hierarchy ─────────────────────────────────────────────────────────────────

export interface Group {
  id: string
  ref: string
  name: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface Brand {
  id: string
  ref: string
  group_id: string
  name: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface Site {
  id: string
  ref: string
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
  ref: string
  email: string
  name: string
  role: 'admin' | 'reseller_staff'
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

// ── Catalog types ─────────────────────────────────────────────────────────────

export interface Category {
  id: string
  brand_id: string
  name: string
  is_system: boolean
  is_active: boolean
}

export interface TaxCategory {
  id: string
  brand_id: string
  name: string
  is_active: boolean
}

export interface TaxRate {
  id: string
  tax_category_id: string
  name: string
  rate_percent: string
  tax_model: 'exclusive' | 'inclusive' | 'compound'
  is_active: boolean
}

export interface Product {
  id: string
  brand_id: string
  category_id: string
  tax_category_id: string | null
  sku: string | null
  name: string
  description: string | null
  base_price_cents: number
  display_order: number
  is_active: boolean
  created_at: string
}

// ── Access grant types ────────────────────────────────────────────────────────

export interface AccessProfile {
  id: string
  brand_id: string
  name: string
  is_system: boolean
  is_active: boolean
  can_access_portal: boolean
}

export interface POSUser {
  id: string
  ref: string
  brand_id: string
  name: string
  email: string
  is_active: boolean
  has_portal_access: boolean
  created_at: string
}

export interface AccessGrant {
  id: string
  user_id: string
  scope: 'site' | 'brand' | 'group'
  site_id: string | null
  brand_id: string | null
  group_id: string | null
  access_profile_id: string
  granted_by_id: string | null
  is_active: boolean
  created_at: string
}

// ── Report types ──────────────────────────────────────────────────────────────

export interface DailySales {
  brand_id: string
  site_id: string
  sale_date: string
  invoice_count: number
  subtotal_cents: number
  tax_cents: number
  discount_cents: number
  total_cents: number
}
