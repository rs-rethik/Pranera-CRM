import { __ } from '@/translation'
import { getSite } from './site'

const NUMBER_FORMATS = {
	'#,###.##': { decimal: '.', group: ',', precision: 2 },
	'#.###,##': { decimal: ',', group: '.', precision: 2 },
	'# ###.##': { decimal: '.', group: ' ', precision: 2 },
	'# ###,##': { decimal: ',', group: ' ', precision: 2 },
	"#'###.##": { decimal: '.', group: "'", precision: 2 },
	'#, ###.##': { decimal: '.', group: ', ', precision: 2 },
	'#,##,###.##': { decimal: '.', group: ',', precision: 2, indian: true },
	'#,###.###': { decimal: '.', group: ',', precision: 3 },
	'#.###': { decimal: '', group: '.', precision: 0 },
	'#,###': { decimal: '', group: ',', precision: 0 },
}

function groupInteger(digits, { group, indian }) {
	if (digits.length <= 3) return digits
	if (!indian) return digits.replace(/\B(?=(\d{3})+(?!\d))/g, group)
	const last3 = digits.slice(-3)
	const rest = digits.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, group)
	return rest + group + last3
}

/** Format a number the way the site's System Settings say (number_format + precision). */
export function formatNumber(value, { precision, site = getSite() } = {}) {
	const number = Number(value)
	if (value === null || value === undefined || value === '' || Number.isNaN(number)) return ''

	const format = NUMBER_FORMATS[site.number_format] || NUMBER_FORMATS['#,###.##']
	const decimals = precision ?? format.precision
	const [integer, fraction = ''] = Math.abs(number).toFixed(decimals).split('.')
	const sign = number < 0 ? '-' : ''

	return sign + groupInteger(integer, format) + (fraction ? format.decimal + fraction : '')
}

/** Inverse of formatNumber: text typed in the site's number format -> a number, or null if it isn't one. */
export function parseNumber(text, site = getSite()) {
	const format = NUMBER_FORMATS[site.number_format] || NUMBER_FORMATS['#,###.##']
	let cleaned = String(text ?? '').trim()
	if (!cleaned) return null
	cleaned = cleaned.split(format.group.trim() || format.group).join('')
	if (format.decimal && format.decimal !== '.') cleaned = cleaned.replace(format.decimal, '.')
	cleaned = cleaned.replace(/[^\d.-]/g, '')
	const number = Number.parseFloat(cleaned)
	return Number.isNaN(number) ? null : number
}

/** 'YYYY-MM-DD' (or a datetime) -> the site's date_format (yyyy-mm-dd, dd-mm-yyyy, mm/dd/yyyy, ...). */
export function formatDate(value, site = getSite()) {
	const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(value ?? ''))
	if (!match) return String(value ?? '')
	const [, yyyy, mm, dd] = match
	return (site.date_format || 'yyyy-mm-dd')
		.replace('yyyy', yyyy)
		.replace('mm', mm)
		.replace('dd', dd)
}

export function formatDatetime(value, site = getSite()) {
	const match = /^\d{4}-\d{2}-\d{2}[ T](\d{2}):(\d{2})(?::(\d{2}))?/.exec(String(value ?? ''))
	if (!match) return formatDate(value, site)
	const [, hh, mi, ss = '00'] = match
	const time = (site.time_format || 'HH:mm:ss') === 'HH:mm' ? `${hh}:${mi}` : `${hh}:${mi}:${ss}`
	return `${formatDate(value, site)} ${time}`
}

/** A value as the user sees it in CRM: dates, numbers and currency follow the site's settings. */
export function formatValue(field, value, site = getSite()) {
	if (value === null || value === undefined || value === '') return ''

	switch (field?.fieldtype) {
		case 'Check':
			return value ? __('Yes') : __('No')
		case 'Date':
			return formatDate(value, site)
		case 'Datetime':
			return formatDatetime(value, site)
		case 'Int':
			return formatNumber(value, { precision: 0, site })
		case 'Float':
		case 'Percent':
			return formatNumber(value, { precision: site.float_precision, site })
		case 'Currency': {
			const amount = formatNumber(value, { precision: site.currency_precision, site })
			return site.currency_symbol ? `${site.currency_symbol} ${amount}` : amount
		}
		default:
			return String(value)
	}
}
