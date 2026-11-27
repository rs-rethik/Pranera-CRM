import { __ } from '@/translation'
import { formatNumber } from './format'
import { getSite } from './site'

export const API = 'pranera_crm.deal_dashboard.api'

export const PRESETS = [
	{ value: 'today', label: __('Today') },
	{ value: 'this_week', label: __('This week') },
	{ value: 'this_month', label: __('This month') },
	{ value: 'this_year', label: __('This year') },
	{ value: 'custom', label: __('Custom range') },
]

export const GRANULARITIES = [
	{ value: 'day', label: __('Daily') },
	{ value: 'week', label: __('Weekly') },
	{ value: 'month', label: __('Monthly') },
	{ value: 'year', label: __('Yearly') },
]

// the trend grouping a preset starts with; the user can change it
const PRESET_GRANULARITY = {
	today: 'day',
	this_week: 'day',
	this_month: 'week',
	this_year: 'month',
	custom: 'week',
}

export const DEFAULTS = {
	preset: 'this_month',
	granularity: 'week',
	from: '',
	to: '',
	persons: [],
	territory: '',
}

export const NO_SALES_PERSON = '__none__'

const iso = (date) =>
	`${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(
		date.getDate()
	).padStart(2, '0')}`

/** First and last day of a preset, as YYYY-MM-DD. Weeks start on Monday. */
export function presetRange(preset, today = new Date()) {
	const year = today.getFullYear()
	const month = today.getMonth()
	const day = today.getDate()
	const monday = day - ((today.getDay() + 6) % 7)
	const ranges = {
		today: [today, today],
		this_week: [new Date(year, month, monday), new Date(year, month, monday + 6)],
		this_month: [new Date(year, month, 1), new Date(year, month + 1, 0)],
		this_year: [new Date(year, 0, 1), new Date(year, 11, 31)],
	}
	const [from, to] = ranges[preset] || ranges.this_month
	return { from: iso(from), to: iso(to) }
}

export function granularityFor(preset) {
	return PRESET_GRANULARITY[preset] || DEFAULTS.granularity
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/

/** The filters a dashboard link carries; anything missing or malformed is the default. */
export function filtersFromQuery(query = {}) {
	const filters = { ...DEFAULTS, persons: [] }
	if (PRESETS.some((preset) => preset.value === query.preset)) filters.preset = query.preset
	filters.granularity = GRANULARITIES.some((g) => g.value === query.granularity)
		? query.granularity
		: granularityFor(filters.preset)
	if (typeof query.territory === 'string') filters.territory = query.territory
	if (typeof query.persons === 'string' && query.persons) {
		filters.persons = query.persons.split('|').filter(Boolean)
	}
	if (filters.preset === 'custom') {
		const valid =
			ISO_DATE.test(query.from) && ISO_DATE.test(query.to) && query.from <= query.to
		if (valid) Object.assign(filters, { from: query.from, to: query.to })
		else
			Object.assign(filters, {
				preset: DEFAULTS.preset,
				granularity: granularityFor(DEFAULTS.preset),
			})
	}
	return filters
}

/** Only what differs from the defaults, so a plain link stays short. */
export function queryFromFilters(filters) {
	const query = {}
	if (filters.preset !== DEFAULTS.preset) query.preset = filters.preset
	if (filters.granularity !== granularityFor(filters.preset))
		query.granularity = filters.granularity
	if (filters.territory) query.territory = filters.territory
	if (filters.persons?.length) query.persons = filters.persons.join('|')
	if (filters.preset === 'custom') Object.assign(query, { from: filters.from, to: filters.to })
	return query
}

export function dateRange(filters) {
	if (filters.preset === 'custom') return { from: filters.from, to: filters.to }
	return presetRange(filters.preset)
}

export function apiParams(filters) {
	const { from, to } = dateRange(filters)
	return {
		from_date: from,
		to_date: to,
		granularity: filters.granularity,
		sales_persons: filters.persons?.length ? JSON.stringify(filters.persons) : '',
		territory: filters.territory,
	}
}

const indianSite = (site) => site.currency === 'INR' || site.number_format === '#,##,###.##'

/** Kilograms: 1,25,000 Kg in full; tonnes from 10,000 kg when `short`. */
export function formatKgs(value, { short = false, site = getSite() } = {}) {
	const kgs = Number(value) || 0
	if (short && Math.abs(kgs) >= 10000) {
		const tonnes = kgs / 1000
		const precision = Math.abs(tonnes) >= 100 ? 0 : 1
		return `${formatNumber(tonnes, { precision, site })} t`
	}
	const precision = Number.isInteger(kgs) || Math.abs(kgs) >= 100 ? 0 : 1
	return `${formatNumber(kgs, { precision, site })} Kg`
}

const INDIAN_UNITS = [
	[1e7, __('Cr')],
	[1e5, __('L')],
]
const WESTERN_UNITS = [
	[1e9, 'B'],
	[1e6, 'M'],
	[1e3, 'K'],
]

/** A short amount for cards and axes: ₹ 3.2 L, ₹ 1.25 Cr, $ 4.5 M. */
export function compactAmount(value, site = getSite()) {
	const number = Number(value) || 0
	const symbol = site.currency_symbol ? `${site.currency_symbol} ` : ''
	const units = indianSite(site) ? INDIAN_UNITS : WESTERN_UNITS
	const unit = units.find(([size]) => Math.abs(number) >= size)
	if (!unit) return symbol + formatNumber(number, { precision: 0, site })
	const scaled = number / unit[0]
	const precision = Math.abs(scaled) >= 100 ? 0 : Math.abs(scaled) >= 10 ? 1 : 2
	return `${symbol}${trimZeros(formatNumber(scaled, { precision, site }))} ${unit[1]}`
}

/** The full amount with the site's grouping, for tooltips and tables. */
export function fullAmount(value, site = getSite()) {
	const amount = formatNumber(Number(value) || 0, { precision: 0, site })
	return site.currency_symbol ? `${site.currency_symbol} ${amount}` : amount
}

function trimZeros(text) {
	return /[.,]\d*0$/.test(text) ? text.replace(/([.,]\d*?)0+$/, '$1').replace(/[.,]$/, '') : text
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** A trend bar's label: '27 Nov', 'w/c 23 Nov', 'Nov 2026' or '2026'. */
export function periodLabel(period, unit) {
	const [year, month, day] = period.split('-').map(Number)
	const name = __(MONTHS[month - 1])
	if (unit === 'year') return String(year)
	if (unit === 'month') return `${name} ${year}`
	if (unit === 'week') return __('w/c {0}', [`${day} ${name}`])
	return `${day} ${name}`
}

export function personLabel(person) {
	return person || __('No Sales Person')
}
