import { afterEach, describe, expect, it } from 'vitest'
import { formatDate, formatDatetime, formatNumber, formatValue, parseNumber } from '@/lib/format'
import { __, setTranslations } from '@/translation'

const site = (over = {}) => ({
  date_format: 'dd-mm-yyyy',
  time_format: 'HH:mm:ss',
  number_format: '#,###.##',
  float_precision: 3,
  currency_precision: 2,
  currency_symbol: '₹',
  ...over,
})

describe('translation (same contract as CRM)', () => {
  afterEach(() => setTranslations({}))

  it('falls back to English and fills {0} placeholders', () => {
    expect(__('Next')).toBe('Next')
    expect(__('{0} is required', ['Status'])).toBe('Status is required')
  })

  it('uses the boot translations, including placeholders and context', () => {
    setTranslations({ Next: 'Weiter', '{0} is required': '{0} ist erforderlich', 'Open:menu': 'Öffnen (Menü)' })
    expect(__('Next')).toBe('Weiter')
    expect(__('{0} is required', ['Status'])).toBe('Status ist erforderlich')
    expect(__('Open', [], 'menu')).toBe('Öffnen (Menü)')
    expect(__('Open')).toBe('Open')
  })
})

describe('number format follows System Settings', () => {
  it('parses what formatNumber produces', () => {
    expect(parseNumber('1,234,567.89', site())).toBe(1234567.89)
    expect(parseNumber('1.234.567,89', site({ number_format: '#.###,##' }))).toBe(1234567.89)
    expect(parseNumber('12,34,567.50', site({ number_format: '#,##,###.##' }))).toBe(1234567.5)
    expect(parseNumber('', site())).toBeNull()
    expect(parseNumber('abc', site())).toBeNull()
  })

  it('handles the common separators', () => {
    expect(formatNumber(1234567.891, { site: site(), precision: 2 })).toBe('1,234,567.89')
    expect(formatNumber(1234567.891, { site: site({ number_format: '#.###,##' }), precision: 2 })).toBe('1.234.567,89')
    expect(formatNumber(1234567.891, { site: site({ number_format: '# ###.##' }), precision: 2 })).toBe('1 234 567.89')
    expect(formatNumber(1234567.891, { site: site({ number_format: "#'###.##" }), precision: 2 })).toBe("1'234'567.89")
  })

  it('groups the Indian way', () => {
    const indian = site({ number_format: '#,##,###.##' })
    expect(formatNumber(1234567.5, { site: indian, precision: 2 })).toBe('12,34,567.50')
    expect(formatNumber(999, { site: indian, precision: 0 })).toBe('999')
    expect(formatNumber(100000, { site: indian, precision: 0 })).toBe('1,00,000')
  })

  it('keeps sign and skips the decimals for integer formats', () => {
    expect(formatNumber(-1234.5, { site: site(), precision: 2 })).toBe('-1,234.50')
    expect(formatNumber(1234, { site: site({ number_format: '#,###' }) })).toBe('1,234')
    expect(formatNumber('', { site: site() })).toBe('')
  })
})

describe('dates follow date_format / time_format', () => {
  it('reorders the date', () => {
    expect(formatDate('2026-09-21', site())).toBe('21-09-2026')
    expect(formatDate('2026-09-21', site({ date_format: 'mm/dd/yyyy' }))).toBe('09/21/2026')
    expect(formatDate('2026-09-21', site({ date_format: 'dd.mm.yyyy' }))).toBe('21.09.2026')
    expect(formatDate('not a date', site())).toBe('not a date')
  })

  it('formats datetimes and honours the time format', () => {
    expect(formatDatetime('2026-09-21 14:05:09', site())).toBe('21-09-2026 14:05:09')
    expect(formatDatetime('2026-09-21 14:05:09', site({ time_format: 'HH:mm' }))).toBe('21-09-2026 14:05')
  })
})

describe('formatValue by field type', () => {
  it('formats currency with the site symbol and precision', () => {
    expect(formatValue({ fieldtype: 'Currency' }, 1500000, site({ number_format: '#,##,###.##' }))).toBe('₹ 15,00,000.00')
    expect(formatValue({ fieldtype: 'Float' }, 1.5, site())).toBe('1.500')
    expect(formatValue({ fieldtype: 'Int' }, 12345, site())).toBe('12,345')
  })

  it('shows dates, checks and plain text', () => {
    expect(formatValue({ fieldtype: 'Date' }, '2026-01-02', site())).toBe('02-01-2026')
    expect(formatValue({ fieldtype: 'Check' }, 1, site())).toBe('Yes')
    expect(formatValue({ fieldtype: 'Check' }, 0, site())).toBe('No')
    expect(formatValue({ fieldtype: 'Data' }, 'abc', site())).toBe('abc')
    expect(formatValue({ fieldtype: 'Data' }, '', site())).toBe('')
  })
})
