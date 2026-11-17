import { __ } from '@/translation'

const UNSUPPORTED = new Set([
	'Attach',
	'Attach Image',
	'Table',
	'Table MultiSelect',
	'HTML',
	'Button',
	'Geolocation',
	'Signature',
	'Image',
	'Barcode',
	'Heading',
])

const LAYOUT_TYPES = new Set(['Tab Break', 'Section Break', 'Column Break'])

export function isSupported(field) {
	return !UNSUPPORTED.has(field.fieldtype)
}

export function isEmpty(value) {
	return (
		value === null ||
		value === undefined ||
		value === '' ||
		(Array.isArray(value) && !value.length)
	)
}

/** All renderable fields of a layout in display order. */
export function flattenLayout(tabs) {
	const out = []
	for (const tab of tabs || []) {
		for (const section of tab.sections || []) {
			for (const column of section.columns || []) {
				for (const field of column.fields || []) {
					if (field && typeof field === 'object' && !LAYOUT_TYPES.has(field.fieldtype))
						out.push(field)
				}
			}
		}
	}
	return out
}

/**
 * Should the client insist on a value? Fields the wizard cannot render, that
 * are conditional (depends_on), hidden or read-only are left to the server.
 */
export function isClientRequired(field) {
	return (
		!!field.reqd &&
		field.fieldtype !== 'Check' &&
		isSupported(field) &&
		!field.hidden &&
		!field.read_only &&
		!field.depends_on
	)
}

export function selectOptions(field) {
	const values = String(field.options || '')
		.split('\n')
		.map((o) => o.trim())
		.filter(Boolean)
	return field.reqd ? values : ['', ...values]
}

/** Sections that contain at least one visible field, for compact rendering. */
export function visibleSections(tab) {
	return (tab.sections || [])
		.map((section) => ({
			...section,
			columns: (section.columns || [])
				.map((column) => ({
					...column,
					fields: (column.fields || []).filter(
						(f) => f && typeof f === 'object' && !f.hidden
					),
				}))
				.filter((column) => column.fields.length),
		}))
		.filter((section) => section.columns.length)
}

/**
 * Why a candidate matched the lead. The strings are literal `__()` calls so the
 * translation extractor can find them (a dynamic `__(reason)` would be invisible to it).
 */
export function matchReason(reason) {
	const reasons = {
		email: __('email'),
		phone: __('phone'),
		mobile: __('mobile number'),
		name: __('name'),
		website: __('website'),
		'name and website': __('name and website'),
	}
	return reasons[reason] || reason
}
