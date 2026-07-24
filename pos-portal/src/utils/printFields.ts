/**
 * Client-side mirror of app/constants/print_fields.py's field catalog — which
 * fields are selectable per template_type/section, and their labels. The
 * backend independently validates every field_key on save (422 if invalid),
 * so a catalog drift here is caught immediately rather than silently
 * accepted, not a data-integrity risk — kept as a plain static mirror rather
 * than a new reference-data API round trip for a list this small and stable.
 */

import type { PrintFieldSection, PrintTemplateType } from '../types'

export interface PrintFieldDefinition {
  key: string
  label: string
  section: PrintFieldSection
}

const COMMON_HEADER_FOOTER: PrintFieldDefinition[] = (['header', 'footer'] as const).flatMap((section) => [
  { key: 'LOGO', label: 'Logo', section },
  { key: 'BRAND_NAME', label: 'Brand name', section },
  { key: 'STORE_NAME', label: 'Store name', section },
  { key: 'ADDRESS', label: 'Address', section },
  { key: 'STORE_PHONE', label: 'Store phone', section },
  { key: 'ABN', label: 'ABN / Tax ID', section },
  { key: 'DATE_TIME', label: 'Date/time', section },
  { key: 'SERVED_BY', label: 'Served by', section },
  { key: 'FREE_TEXT', label: 'Free text', section },
  { key: 'DIVIDER', label: 'Divider line', section },
])

const ORDER_HEADER_FOOTER: PrintFieldDefinition[] = (['header', 'footer'] as const).flatMap((section) => [
  { key: 'INVOICE_NUMBER', label: 'Invoice number', section },
  { key: 'ORDER_NOTES', label: 'Order notes', section },
])

const ORDER_ITEMS: PrintFieldDefinition[] = [
  { key: 'PRODUCT_LINE', label: 'Product line (name / qty / price)', section: 'items' },
  { key: 'MODIFIER_LINE', label: 'Modifier line', section: 'items' },
  { key: 'ITEM_NOTES', label: 'Item notes', section: 'items' },
]

const REGISTER_SUMMARY_ONLY: PrintFieldDefinition[] = [
  { key: 'PAYMENT_METHOD_BREAKDOWN', label: 'Payment method breakdown', section: 'items' },
  { key: 'CASH_VARIANCE', label: 'Cash variance', section: 'footer' },
  { key: 'OPENING_CLOSING_CASH', label: 'Opening/closing cash', section: 'footer' },
]

const CASH_IN_SLIP_ONLY: PrintFieldDefinition[] = [
  { key: 'CASH_IN_AMOUNT', label: 'Cash-in amount', section: 'footer' },
  { key: 'COUNTED_BY', label: 'Counted by', section: 'footer' },
]

export const TEMPLATE_TYPE_FIELDS: Record<PrintTemplateType, PrintFieldDefinition[]> = {
  invoice: [...COMMON_HEADER_FOOTER, ...ORDER_HEADER_FOOTER, ...ORDER_ITEMS],
  docket: [...COMMON_HEADER_FOOTER, ...ORDER_HEADER_FOOTER, ...ORDER_ITEMS],
  register_summary: [...COMMON_HEADER_FOOTER, ...REGISTER_SUMMARY_ONLY],
  cash_in_slip: [...COMMON_HEADER_FOOTER, ...CASH_IN_SLIP_ONLY],
}

/** Fields selectable for one section of a given template type. */
export function fieldsForSection(templateType: PrintTemplateType, section: PrintFieldSection): PrintFieldDefinition[] {
  return TEMPLATE_TYPE_FIELDS[templateType].filter((f) => f.section === section)
}

/** Human-readable label for a field_key, falling back to the raw key if unrecognised. */
export function fieldLabel(templateType: PrintTemplateType, fieldKey: string): string {
  return TEMPLATE_TYPE_FIELDS[templateType].find((f) => f.key === fieldKey)?.label ?? fieldKey
}

export const TEMPLATE_TYPE_LABELS: Record<PrintTemplateType, string> = {
  invoice: 'Invoice',
  docket: 'Order Docket',
  register_summary: 'Register Summary',
  cash_in_slip: 'Cash-in Slip',
}

export const SECTION_LABELS: Record<PrintFieldSection, string> = {
  header: 'Header',
  items: 'Items',
  footer: 'Footer',
}
