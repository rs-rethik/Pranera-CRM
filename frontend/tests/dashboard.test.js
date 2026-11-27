import { describe, expect, it } from 'vitest'
import {
	DEFAULTS,
	apiParams,
	compactAmount,
	filtersFromQuery,
	formatKgs,
	granularityFor,
	periodLabel,
	presetRange,
	queryFromFilters,
} from '@/lib/dashboard'

const INR = { currency: 'INR', currency_symbol: '₹', number_format: '#,##,###.##' }
const USD = { currency: 'USD', currency_symbol: '$', number_format: '#,###.##' }

describe('presetRange', () => {
	const friday = new Date(2026, 10, 27) // Friday 27 Nov 2026

	it('gives the first and last day of each preset', () => {
		expect(presetRange('today', friday)).toEqual({ from: '2026-11-27', to: '2026-11-27' })
		expect(presetRange('this_week', friday)).toEqual({ from: '2026-11-23', to: '2026-11-29' })
		expect(presetRange('this_month', friday)).toEqual({ from: '2026-11-01', to: '2026-11-30' })
		expect(presetRange('this_year', friday)).toEqual({ from: '2026-01-01', to: '2026-12-31' })
	})

	it('starts the week on Monday, also on a Sunday', () => {
		expect(presetRange('this_week', new Date(2026, 10, 29))).toEqual({
			from: '2026-11-23',
			to: '2026-11-29',
		})
	})
})

describe('filters in the URL', () => {
	it('reads nothing as the defaults', () => {
		expect(filtersFromQuery({})).toEqual(DEFAULTS)
	})

	it('keeps a plain link short and the grouping that goes with the period implicit', () => {
		expect(queryFromFilters({ ...DEFAULTS })).toEqual({})
		const year = { ...DEFAULTS, preset: 'this_year', granularity: granularityFor('this_year') }
		expect(queryFromFilters(year)).toEqual({ preset: 'this_year' })
	})

	it('round-trips Sales Persons, territory, grouping and a custom range', () => {
		const filters = {
			...DEFAULTS,
			preset: 'custom',
			from: '2026-10-01',
			to: '2026-10-15',
			granularity: 'day',
			persons: ['Kaviya', 'Mahendran K'],
			territory: 'KONGU',
		}
		expect(filtersFromQuery(queryFromFilters(filters))).toEqual(filters)
	})

	it('drops a malformed range, preset or grouping', () => {
		expect(filtersFromQuery({ preset: 'custom', from: 'soon', to: '2026-10-01' })).toEqual(
			DEFAULTS
		)
		expect(filtersFromQuery({ preset: 'forever' }).preset).toBe('this_month')
		expect(filtersFromQuery({ granularity: 'hourly' }).granularity).toBe('week')
	})

	it('sends the Sales Persons as a JSON list', () => {
		const params = apiParams({ ...DEFAULTS, persons: ['Kaviya'] })
		expect(params.sales_persons).toBe('["Kaviya"]')
		expect(apiParams({ ...DEFAULTS }).sales_persons).toBe('')
	})
})

describe('formatKgs', () => {
	it('groups kilograms the Indian way', () => {
		expect(formatKgs(125000, { site: INR })).toBe('1,25,000 Kg')
		expect(formatKgs(12.5, { site: INR })).toBe('12.5 Kg')
	})

	it('shows tonnes from 10,000 kg when short', () => {
		expect(formatKgs(9999, { short: true, site: INR })).toBe('9,999 Kg')
		expect(formatKgs(18400, { short: true, site: INR })).toBe('18.4 t')
		expect(formatKgs(339198, { short: true, site: INR })).toBe('339 t')
	})
})

describe('compactAmount', () => {
	it('writes rupees in lakh and crore', () => {
		expect(compactAmount(85000, INR)).toBe('₹ 85,000')
		expect(compactAmount(320000, INR)).toBe('₹ 3.2 L')
		expect(compactAmount(12500000, INR)).toBe('₹ 1.25 Cr')
	})

	it('writes other currencies in thousands and millions', () => {
		expect(compactAmount(1200000, USD)).toBe('$ 1.2 M')
	})
})

describe('periodLabel', () => {
	it('names a day, a week, a month and a year', () => {
		expect(periodLabel('2026-11-27', 'day')).toBe('27 Nov')
		expect(periodLabel('2026-11-23', 'week')).toBe('w/c 23 Nov')
		expect(periodLabel('2026-11-01', 'month')).toBe('Nov 2026')
		expect(periodLabel('2026-01-01', 'year')).toBe('2026')
	})
})
