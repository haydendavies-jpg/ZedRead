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

/**
 * One selectable identity when an email is shared by a SuperAdmin and a
 * portal-capable User (ROLE_MODEL.md §3 cross-identity disambiguation).
 */
export interface IdentitySummary {
  identity_type: 'superadmin' | 'user'
  display_name: string
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
  /**
   * Set instead of a token when the same email matches both a SuperAdmin and a
   * portal-capable User — the caller picks one and calls /auth/portal/identity-token.
   */
  available_identities?: IdentitySummary[]
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
  ref: string
  brand_id: string
  reporting_group_id: string
  name: string
  is_system: boolean
  is_active: boolean
  display_order: number
  default_color: string
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
  ref: string
  brand_id: string
  category_id: string
  tax_category_id: string | null
  name: string
  description: string | null
  print_name: string | null
  effective_print_name: string
  base_price_cents: number
  price_ex_cents: number
  is_taxable: boolean
  is_open_item: boolean
  photo_url: string | null
  display_order: number
  is_active: boolean
}

/** GET /products row shape — Product plus its joined Category/Reporting Group names (Stage 20). */
export interface ProductListItem extends Product {
  category_name: string
  category_color: string
  reporting_group_id: string
  reporting_group_name: string
  /** Comma-joined names of this product's active linked modifier groups, or null if none. */
  modifier_names: string | null
}

// ── Modifiers & comboing (Menu Studio redesign) ─────────────────────────────────

export interface ModifierGroup {
  id: string
  brand_id: string
  name: string
  min_selections: number
  max_selections: number
  /** True — the same option may be selected multiple times on the POS (up to max_selections total). */
  has_quantity: boolean
  is_active: boolean
}

export interface ModifierOption {
  id: string
  modifier_group_id: string
  name: string
  price_delta_cents: number
  display_order: number
  is_active: boolean
}

export interface LinkedGroupOption {
  id: string
  name: string
  price_delta_cents: number
}

export interface LinkedGroup {
  id: string
  name: string
  min_selections: number
  max_selections: number
  options: LinkedGroupOption[]
}

export interface ModifierOptionDetail extends ModifierOption {
  linked_groups: LinkedGroup[]
}

export interface ModifierGroupDetail extends ModifierGroup {
  options: ModifierOptionDetail[]
  used_by_count: number
}

// ── Menus (distinct from a POS MenuLayout) ──────────────────────────────────────

export interface Menu {
  id: string
  ref: string
  brand_id: string
  site_id: string | null
  scope: 'brand' | 'site'
  menu_layout_id: string | null
  name: string
  note: string | null
  status: 'draft' | 'scheduled' | 'published'
  scheduled_at: string | null
  published_at: string | null
  created_at: string
  updated_at: string
}

// ── Variants & Combos (Stage 22) ────────────────────────────────────────────────

export interface AttributeAssignment {
  attribute_type_id: string
  attribute_value_id: string
}

export interface Variant {
  id: string
  ref: string
  product_id: string
  sku: string | null
  price_cents: number | null
  display_name: string | null
  is_active: boolean
  attributes: AttributeAssignment[]
}

/** GET /variants row shape — Variant plus its joined parent product's name/ref. */
export interface VariantListItem extends Variant {
  product_name: string
  product_ref: string
}

export interface ComboGroup {
  id: string
  ref: string
  product_id: string
  name: string
  display_name: string | null
  min_selections: number
  max_selections: number
  is_required: boolean
  display_order: number
  is_active: boolean
}

/** GET /combos row shape — ComboGroup plus its joined parent product's name/ref. */
export interface ComboGroupListItem extends ComboGroup {
  product_name: string
  product_ref: string
}

// ── POS Menu Builder (Stage 23; Phase 2 grid editor) ────────────────────────────

export type MenuButtonKind = 'product' | 'folder'

export interface MenuButton {
  id: string
  tab_id: string
  kind: MenuButtonKind
  product_ref: string | null
  child_tab_id: string | null
  width: number
  height: number
  color: string | null
  display_order: number
  /** Resolved live from the brand's catalog by product_ref — null if the ref no longer resolves, or kind='folder'. */
  product_name: string | null
  price_cents: number | null
  is_active: boolean | null
  /** The linked product's category default colour — powers the inspector's "Category default" reset. */
  category_color: string | null
  /** Set only when kind='folder' — the nested tab this button opens. */
  child_tab_name: string | null
  child_tab_button_count: number | null
}

export interface MenuTab {
  id: string
  layout_id: string
  parent_tab_id: string | null
  name: string
  color: string | null
  display_order: number
  buttons: MenuButton[]
}

export interface MenuLayout {
  id: string
  brand_id: string
  site_id: string | null
  scope: 'brand' | 'site'
  name: string
  color: string
  is_published: boolean
  published_at: string | null
  version: number
  is_all_day: boolean
  start_time: string | null
  end_time: string | null
  /** 0=Monday .. 6=Sunday. */
  active_days: number[]
  scheduled_publish_at: string | null
  button_count: number
  created_at: string
  updated_at: string
}

export interface MenuLayoutDetail extends MenuLayout {
  tabs: MenuTab[]
}

export interface PublishWarning {
  button_id: string
  tab_name: string
  product_ref: string
  reason: 'product_not_found' | 'product_inactive'
}

export interface PublishResult {
  layout: MenuLayout
  warnings: PublishWarning[]
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

// ── Page-category permission hierarchy (ROLE_MODEL.md §4/§6, Stage 18) ─────────
//
// Mirrors app.constants.pages.PAGE_CATALOG for rendering only — page_key
// validity is enforced server-side (grant/revoke 422s on an unknown key).
// Every stage that ships a new portal page must add its key here in the
// same commit it adds one to pages.py and ROLE_MODEL.md §6.

export type PageCategory =
  | 'product_menus'
  | 'app_configuration'
  | 'reports'
  | 'user_management'
  | 'customers_loyalty'

export const PAGE_CATEGORY_LABELS: Record<PageCategory, string> = {
  product_menus: 'Product & Menus',
  app_configuration: 'App Configuration',
  reports: 'Reports',
  user_management: 'User Management',
  customers_loyalty: 'Customers & Loyalty',
}

export const PAGE_CATALOG: Array<{ key: string; category: PageCategory; label: string }> = [
  { key: 'products', category: 'product_menus', label: 'Products' },
  { key: 'variants_modifiers', category: 'product_menus', label: 'Variants & Modifiers' },
  { key: 'combos', category: 'product_menus', label: 'Combos' },
  { key: 'categories', category: 'product_menus', label: 'Categories' },
  { key: 'reporting_groups', category: 'product_menus', label: 'Reporting Groups' },
  { key: 'site_settings', category: 'app_configuration', label: 'Site Settings' },
  { key: 'devices', category: 'app_configuration', label: 'Devices' },
  { key: 'tax_settings', category: 'app_configuration', label: 'Tax Settings' },
  { key: 'license_billing', category: 'app_configuration', label: 'License & Billing' },
  { key: 'daily_sales', category: 'reports', label: 'Daily Sales' },
  { key: 'tax_collected', category: 'reports', label: 'Tax Collected' },
  { key: 'invoices', category: 'reports', label: 'Invoices' },
  { key: 'audit_log', category: 'reports', label: 'Audit Log' },
  { key: 'users', category: 'user_management', label: 'Users' },
  { key: 'access_grants', category: 'user_management', label: 'Access Grants' },
  { key: 'access_profiles', category: 'user_management', label: 'Access Profiles' },
  { key: 'customers', category: 'customers_loyalty', label: 'Customers' },
  { key: 'loyalty_programs', category: 'customers_loyalty', label: 'Loyalty Programs' },
]

export interface PagePermissionsResponse {
  access_profile_id: string
  page_keys: string[]
}

export interface VisiblePagesResponse {
  access_profile_id: string
  site_id: string
  page_keys: string[]
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

// ── Invoice reporting types (Stage 21) ─────────────────────────────────────────

export interface InvoiceReportRow {
  id: string
  brand_id: string
  site_id: string
  site_name: string
  brand_name: string
  created_by_id: string | null
  invoice_type: string
  status: string
  subtotal_cents: number
  tax_cents: number
  discount_cents: number
  total_cents: number
  refund_of_id: string | null
  is_refunded: boolean
  voided_at: string | null
  paid_at: string | null
  created_at: string
}

export interface InvoicePayment {
  id: string
  invoice_id: string
  method: string
  amount_cents: number
  reference: string | null
  paid_at: string
}

export interface InvoiceDetailModifier {
  id: string
  modifier_name: string
  price_delta_cents: number
}

export interface InvoiceDetailLineItem {
  id: string
  product_id: string | null
  product_name: string
  unit_price_cents: number
  quantity: number
  subtotal_cents: number
  tax_cents: number
  line_total_cents: number
  display_order: number
  modifiers: InvoiceDetailModifier[]
}

export interface InvoiceDetailTaxRow {
  id: string
  tax_rate_name: string
  rate_percent: string
  tax_model: string
  taxable_amount_cents: number
  tax_amount_cents: number
}

export interface InvoiceDetail {
  id: string
  brand_id: string
  site_id: string
  site_name: string
  brand_name: string
  created_by_id: string | null
  invoice_type: string
  status: string
  subtotal_cents: number
  tax_cents: number
  discount_cents: number
  discount_reason: string | null
  total_cents: number
  refund_of_id: string | null
  is_refunded: boolean
  voided_at: string | null
  paid_at: string | null
  created_at: string
  line_items: InvoiceDetailLineItem[]
  tax_breakdown: InvoiceDetailTaxRow[]
  payments: InvoicePayment[]
}

export interface InvoiceChangeLogEntry {
  id: string
  action: string
  actor_name: string | null
  actor_email: string | null
  actor_type: string
  before_state: Record<string, unknown> | null
  after_state: Record<string, unknown> | null
  created_at: string
}
