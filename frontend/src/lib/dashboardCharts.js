import { formatNumber } from './format'
import { __ } from '@/translation'
import { compactAmount, formatKgs, fullAmount, periodLabel, personLabel } from './dashboard'

// status colours carry meaning here: open is neutral blue, won green, lost red
// one blue for quantities in the pipeline, green for what went out; grey for comparisons
export const COLORS = {
	open: '#318AD8',
	delivered: '#30A66D',
	value: '#1F5F99',
	muted: '#C7C7C7',
	faint: '#E2E2E2',
}

function token(name, fallback) {
	const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
	return value || fallback
}

function theme() {
	return {
		text: token('--ink-gray-6', '#525252'),
		strong: token('--ink-gray-8', '#171717'),
		line: token('--outline-gray-1', '#EDEDED'),
		surface: token('--surface-white', '#FFFFFF'),
	}
}

function base(colors) {
	return {
		animationDuration: 300,
		textStyle: { fontFamily: 'InterVar, Inter, sans-serif', color: colors.text },
		tooltip: {
			trigger: 'axis',
			axisPointer: { type: 'shadow', shadowStyle: { opacity: 0.06 } },
			backgroundColor: colors.surface,
			borderColor: colors.line,
			textStyle: { color: colors.strong, fontSize: 13 },
			extraCssText: 'box-shadow: 0 4px 12px rgba(0,0,0,.08); border-radius: 8px;',
		},
		grid: { left: 4, right: 28, top: 12, bottom: 4, containLabel: true },
	}
}

const valueAxis = (colors, format) => ({
	type: 'value',
	axisLabel: { color: colors.text, fontSize: 12, formatter: format },
	splitLine: { lineStyle: { color: colors.line } },
})
// every tick in one unit: tonnes once the largest bar is 10,000 kg or more
const kgAxis = (colors, values) => {
	const tonnes = Math.max(0, ...values) >= 10000
	return valueAxis(colors, (value) =>
		tonnes ? `${formatNumber(value / 1000, { precision: 0 })} t` : formatKgs(value),
	)
}

const categoryAxis = (colors, labels, extra = {}) => ({
	type: 'category',
	data: labels,
	axisTick: { show: false },
	axisLine: { lineStyle: { color: colors.line } },
	axisLabel: { color: colors.text, fontSize: 12, ...extra },
})

const HTML_ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }
const escapeHTML = (text) => String(text ?? '').replace(/[&<>"']/g, (char) => HTML_ESCAPES[char])

// ECharts puts a tooltip into the page as HTML, and stage, territory, source and reason
// names are typed by users: every piece of text is escaped here, in one place
function tooltipRows(title, rows) {
	const lines = rows
		.map(
			([marker, label, value]) =>
				`<div style="display:flex;gap:16px;justify-content:space-between"><span>${marker}${escapeHTML(
					label,
				)}</span><b>${escapeHTML(value)}</b></div>`,
		)
		.join('')
	return `<div style="font-weight:600;margin-bottom:4px">${escapeHTML(title)}</div>${lines}`
}

const bar = (name, data, color, extra = {}) => ({
	name,
	type: 'bar',
	data,
	itemStyle: { color, borderRadius: 3 },
	barMaxWidth: 28,
	cursor: 'pointer',
	...extra,
})

/** Horizontal bars of Kgs, one per row, labelled with Kgs and deal count. */
export function kgBarsOptions(rows, labelOf, { color = COLORS.open } = {}) {
	const colors = theme()
	const options = base(colors)
	const labels = rows.map(labelOf)
	return {
		...options,
		grid: { ...options.grid, right: 110 },
		tooltip: {
			...options.tooltip,
			formatter: ([point]) => {
				const row = rows[point.dataIndex]
				return tooltipRows(labels[point.dataIndex], [
					['', __('Quantity'), formatKgs(row.kgs)],
					['', __('Deals'), row.deals],
				])
			},
		},
		xAxis: { ...kgAxis(colors, []), axisLabel: { show: false }, splitLine: { show: false } },
		yAxis: {
			...categoryAxis(colors, labels, { width: 130, overflow: 'truncate' }),
			inverse: true,
		},
		series: [
			bar(
				__('Quantity'),
				rows.map((row) => row.kgs),
				color,
				{
					label: {
						show: true,
						position: 'right',
						color: colors.text,
						fontSize: 12,
						formatter: ({ dataIndex }) =>
							`${formatKgs(rows[dataIndex].kgs, { short: true })} · ${
								rows[dataIndex].deals
							}`,
					},
				},
			),
		],
	}
}

export const stageBarsOptions = (stages) => kgBarsOptions(stages, (row) => row.status)
export const personBarsOptions = (people) =>
	kgBarsOptions(people, (row) => personLabel(row.sales_person))

export function deliveredTrendOptions(delivered) {
	const colors = theme()
	const options = base(colors)
	const labels = delivered.trend.map((row) => periodLabel(row.period, delivered.unit))
	return {
		...options,
		tooltip: {
			...options.tooltip,
			formatter: ([point]) => {
				const row = delivered.trend[point.dataIndex]
				return tooltipRows(labels[point.dataIndex], [
					['', __('Delivered'), formatKgs(row.kgs)],
					['', __('Deals'), row.deals],
				])
			},
		},
		xAxis: categoryAxis(colors, labels),
		yAxis: kgAxis(
			colors,
			delivered.trend.map((row) => row.kgs),
		),
		series: [
			bar(
				__('Delivered'),
				delivered.trend.map((row) => row.kgs),
				COLORS.delivered,
			),
		],
	}
}

/** Same dates last year, the period before, and this period: three bars. */
export function comparisonOptions(comparison) {
	const colors = theme()
	const options = base(colors)
	const periods = [
		['last_year', __('Same period last year'), COLORS.faint],
		['previous', __('Previous period'), COLORS.muted],
		['current', __('This period'), COLORS.delivered],
	]
	return {
		...options,
		tooltip: {
			...options.tooltip,
			formatter: ([point]) => {
				const [key, label] = periods[point.dataIndex]
				const period = comparison[key]
				return tooltipRows(label, [
					['', __('Dates'), `${period.from} – ${period.to}`],
					['', __('Delivered'), formatKgs(period.kgs)],
					['', __('Deals'), period.deals],
				])
			},
		},
		xAxis: categoryAxis(
			colors,
			periods.map(([, label]) => label),
		),
		yAxis: kgAxis(
			colors,
			periods.map(([key]) => comparison[key].kgs),
		),
		series: [
			{
				...bar(
					__('Delivered'),
					periods.map(([key, , color]) => ({
						value: comparison[key].kgs,
						itemStyle: { color, borderRadius: 3 },
					})),
					COLORS.delivered,
				),
				barMaxWidth: 56,
				cursor: 'default',
			},
		],
	}
}

export function orderTrendOptions(orders) {
	const colors = theme()
	const options = base(colors)
	const labels = orders.trend.map((row) => periodLabel(row.period, orders.unit))
	return {
		...options,
		tooltip: {
			...options.tooltip,
			formatter: ([point]) => {
				const row = orders.trend[point.dataIndex]
				return tooltipRows(labels[point.dataIndex], [
					['', __('Orders'), row.orders],
					['', __('Quantity'), formatKgs(row.kgs)],
					['', __('Value'), fullAmount(row.value)],
				])
			},
		},
		xAxis: categoryAxis(colors, labels),
		yAxis: valueAxis(colors, (value) => compactAmount(value)),
		series: [
			bar(
				__('Value'),
				orders.trend.map((row) => row.value),
				COLORS.value,
			),
		],
	}
}
