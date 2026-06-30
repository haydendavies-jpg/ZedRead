/** Shared defaults and helpers for Group/Brand/Site company profile forms. */

import type { CompanyProfileValues } from '../components/CompanyProfileFields'

export const DEFAULT_COMPANY_PROFILE_VALUES: CompanyProfileValues = {
  timezone: 'Australia/Sydney',
  currency: 'AUD',
  country: 'AU',
  tax_id_value: '',
  billing_email: '',
}

/** Compares old vs new currency and asks for confirmation, since currency affects invoice display. Returns true if it's safe to proceed. */
export function confirmCurrencyChange(previousCurrency: string, nextCurrency: string, entityLabel: string): boolean {
  if (previousCurrency === nextCurrency) return true
  return window.confirm(
    `Changing currency affects how invoices for this ${entityLabel} are displayed. Continue?`
  )
}
