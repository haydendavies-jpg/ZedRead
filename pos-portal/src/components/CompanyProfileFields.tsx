/** Shared timezone/currency/country/tax-ID/billing-email fields for Group/Brand/Site company profile forms. */

import { useTimezones, useCountries, useCurrencies, useTaxIdLabel } from '../hooks/useReferenceData'

export interface CompanyProfileValues {
  timezone: string
  currency: string
  country: string
  tax_id_value: string
  billing_email: string
}

interface Props {
  values: CompanyProfileValues
  onChange: (values: CompanyProfileValues) => void
}

export function CompanyProfileFields({ values, onChange }: Props) {
  const { data: timezones = [] } = useTimezones()
  const { data: countries = [] } = useCountries()
  const { data: currencies = [] } = useCurrencies()
  const { data: taxIdLabel } = useTaxIdLabel(values.country || null)

  const set = <K extends keyof CompanyProfileValues>(key: K, value: CompanyProfileValues[K]) =>
    onChange({ ...values, [key]: value })

  const selectClass = 'w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500'
  const inputClass = selectClass

  return (
    <>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Timezone</label>
          <select value={values.timezone} onChange={(e) => set('timezone', e.target.value)} required className={selectClass}>
            {timezones.map((tz) => (
              <option key={tz} value={tz}>{tz}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Currency</label>
          <select value={values.currency} onChange={(e) => set('currency', e.target.value)} required className={selectClass}>
            {currencies.map((c) => (
              <option key={c.code} value={c.code}>{c.code} — {c.name}</option>
            ))}
          </select>
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Country</label>
          <select value={values.country} onChange={(e) => set('country', e.target.value)} required className={selectClass}>
            {countries.map((c) => (
              <option key={c.code} value={c.code}>{c.name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{taxIdLabel ?? 'Tax ID'} (optional)</label>
          <input value={values.tax_id_value} onChange={(e) => set('tax_id_value', e.target.value)} className={inputClass} />
        </div>
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Billing email (optional)</label>
        <input
          type="email"
          value={values.billing_email}
          onChange={(e) => set('billing_email', e.target.value)}
          className={inputClass}
          placeholder="billing@example.com"
        />
      </div>
    </>
  )
}
