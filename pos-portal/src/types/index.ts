/** Shared TypeScript types for the ZedRead portal API. */

// ── Auth types ────────────────────────────────────────────────────────────────

export type TokenType = 'portal_access' | 'mgmt_access'

export interface GrantSummary {
  user_id: string
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
  /** Set when this token was issued via admin impersonation. */
  imp_id?: string
  imp_email?: string
  imp_name?: string
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
  /** Set when this session is an admin impersonation. */
  imp_id?: string
  imp_email?: string
  imp_name?: string
}

// ── Hierarchy ─────────────────────────────────────────────────────────────────

export interface Group {
  id: string
  ref: string
  name: string
  is_active: boolean
  timezone: string
  currency: string
  country: string
  tax_id_value: string | null
  logo_url: string | null
  billing_email: string | null
  created_at: string
  updated_at: string
}

export interface Brand {
  id: string
  ref: string
  group_id: string
  name: string
  is_active: boolean
  timezone: string
  currency: string
  country: string
  tax_id_value: string | null
  logo_url: string | null
  billing_email: string | null
  created_at: string
  updated_at: string
}

export interface Site {
  id: string
  ref: string
  brand_id: string
  name: string
  is_active: boolean
  timezone: string
  currency: string
  country: string
  tax_id_value: string | null
  logo_url: string | null
  billing_email: string | null
  address_street: string
  address_city: string
  address_state: string
  address_postcode: string
  created_at: string
  updated_at: string
}

/** ISO code + display name pair returned by the /reference/countries and /reference/currencies routes. */
export interface CodeName {
  code: string
  name: string
}

/** Response shape for POST /{group|brand|site}s/{id}/request-billing-info. */
export interface BillingInfoRequestResponse {
  sent_to: string
  source_level: 'group' | 'brand' | 'site'
}

export interface EmailTemplate {
  id: string
  template_key: string
  name: string
  subject: string
  body: string
  is_system: boolean
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

export interface SuperAdmin {
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
  reporting_group_id: string
  name: string
  is_system: boolean
  is_active: boolean
  display_order: number
}

export interface ReportingGroup {
  id: string
  brand_id: string
  ref: string
  name: string
  is_default: boolean
  is_system: boolean
  created_at: string
  updated_at: string
}

export interface TaxCategory {
  id: string
  brand_id: string
  name: string
  is_active: boolean
  is_system: boolean
  is_tax_free: boolean
}

export interface TaxTemplateRate {
  id: string
  tax_template_id: string
  name: string
  rate_percent: string
  tax_model: 'exclusive' | 'inclusive' | 'compound'
  display_order: number
  is_active: boolean
}

export interface TaxTemplate {
  id: string
  name: string
  country: string
  state: string | null
  county: string | null
  city: string | null
  is_active: boolean
  created_at: string
  updated_at: string
  rates: TaxTemplateRate[]
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
  price_ex_cents: number
  is_taxable: boolean
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

export interface User {
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
