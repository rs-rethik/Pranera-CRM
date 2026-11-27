<template>
	<div class="flex min-h-0 flex-col">
		<ErrorMessage class="mb-2" :message="error" />
		<div v-if="loading && !rows.length" class="flex flex-col gap-2">
			<Skeleton v-for="n in 6" :key="n" class="h-9 w-full rounded" />
		</div>
		<p v-else-if="!rows.length" class="py-10 text-center text-sm text-ink-gray-5">
			{{ emptyText }}
		</p>
		<div v-else class="min-h-0 overflow-auto">
			<table class="w-full min-w-[640px] text-left text-base">
				<thead class="sticky top-0 bg-surface-white text-sm text-ink-gray-5">
					<tr class="border-b border-outline-gray-1">
						<th
							v-for="column in columns"
							:key="column.key"
							class="py-2 pr-3 font-normal last:pr-0"
							:class="[column.class, column.numeric && 'text-right']"
							:aria-sort="
								sort === column.key
									? descending
										? 'descending'
										: 'ascending'
									: 'none'
							"
						>
							<button
								type="button"
								class="inline-flex items-center gap-1 hover:text-ink-gray-8"
								@click="sortBy(column.key)"
							>
								{{ column.label }}
								<span
									v-if="sort === column.key"
									:class="descending ? 'lucide-arrow-down' : 'lucide-arrow-up'"
									class="size-3.5"
									aria-hidden="true"
								/>
							</button>
						</th>
					</tr>
				</thead>
				<tbody>
					<tr
						v-for="row in rows"
						:key="row.name"
						class="cursor-pointer border-b border-outline-gray-1 hover:bg-surface-gray-1"
						@click="open($event, row)"
					>
						<td
							v-for="column in columns"
							:key="column.key"
							class="max-w-0 truncate py-2 pr-3 last:pr-0"
							:class="[
								column.class,
								column.numeric
									? 'text-right tabular-nums text-ink-gray-8'
									: 'text-ink-gray-7',
							]"
						>
							<template v-if="column.key === 'label'">
								<span class="block truncate font-medium text-ink-gray-8">{{
									row.label
								}}</span>
								<span
									v-if="row.label !== row.name"
									class="block truncate text-sm text-ink-gray-5"
								>
									{{ row.name }}
								</span>
							</template>
							<Badge
								v-else-if="column.key === 'status'"
								:label="row.status"
								variant="subtle"
							/>
							<template v-else>{{ display(column, row) }}</template>
						</td>
					</tr>
				</tbody>
			</table>
		</div>
		<div
			v-if="rows.length"
			class="flex items-center justify-between pt-3 text-sm text-ink-gray-5"
		>
			<span>{{ __('{0} of {1}', [rows.length, total]) }}</span>
			<Button
				v-if="rows.length < total"
				:label="__('Load more')"
				:loading="loading"
				@click="load(rows.length)"
			/>
		</div>
	</div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Badge, Button, ErrorMessage, Skeleton } from 'frappe-ui'
import { apiGet, errorMessage } from '@/lib/api'
import { API, formatKgs, fullAmount, personLabel } from '@/lib/dashboard'
import { formatDate } from '@/lib/format'
import { __ } from '@/translation'

const props = defineProps({
	segment: { type: String, required: true },
	value: { type: String, default: '' },
	// the dashboard's filters, as the API takes them
	params: { type: Object, required: true },
	emptyText: { type: String, default: () => __('Nothing here.') },
	pageLength: { type: Number, default: 20 },
})

const embedded = new URLSearchParams(window.location.search).get('embed') === '1'

const CUSTOMER_SEGMENTS = ['active', 'new', 'potential']
const DATE_LABELS = {
	active: __('Last order'),
	new: __('Last order'),
	potential: __('Last deal'),
	pipeline: __('Updated'),
	pipeline_person: __('Updated'),
	delivered: __('Delivered on'),
	sales_orders: __('Order date'),
}
// CRM records open in CRM's own router; ERPNext ones in Desk, in a new tab
const ROUTES = {
	'CRM Deal': (name) => ({ path: `/crm/deals/${encodeURIComponent(name)}`, crm: true }),
	'CRM Organization': (name) => ({
		path: `/crm/organizations/${encodeURIComponent(name)}`,
		crm: true,
	}),
	Customer: (name) => ({ path: `/app/customer/${encodeURIComponent(name)}`, crm: false }),
	'Sales Order': (name) => ({
		path: `/app/sales-order/${encodeURIComponent(name)}`,
		crm: false,
	}),
}

const columns = computed(() => {
	const first = {
		key: 'label',
		label: CUSTOMER_SEGMENTS.includes(props.segment)
			? __('Customer')
			: props.segment === 'sales_orders'
			? __('Customer · Order')
			: __('Deal'),
	}
	const status = { key: 'status', label: __('Stage'), class: 'w-44' }
	const person = { key: 'sales_person', label: __('Sales Person'), class: 'w-44' }
	const kgs = { key: 'kgs', label: __('Quantity'), class: 'w-32', numeric: true }
	const value = { key: 'value', label: __('Value'), class: 'w-32', numeric: true }
	const date = { key: 'date', label: DATE_LABELS[props.segment], class: 'w-32' }
	if (props.segment === 'sales_orders') return [first, person, kgs, value, date]
	if (CUSTOMER_SEGMENTS.includes(props.segment)) return [first, person, date, kgs]
	return [first, status, person, kgs, date]
})

const rows = ref([])
const total = ref(0)
const loading = ref(false)
const error = ref('')
const sort = ref(CUSTOMER_SEGMENTS.includes(props.segment) ? 'kgs' : 'date')
const descending = ref(true)
let request = 0

async function load(start = 0) {
	const current = ++request
	loading.value = true
	error.value = ''
	try {
		const page = await apiGet(`${API}.get_rows`, {
			...props.params,
			segment: props.segment,
			value: props.value,
			sort: sort.value,
			descending: descending.value ? 1 : 0,
			start,
			page_length: props.pageLength,
		})
		if (current !== request) return // a newer request won
		rows.value = start ? [...rows.value, ...page.rows] : page.rows
		total.value = page.total
	} catch (err) {
		if (current === request) error.value = errorMessage(err)
	} finally {
		if (current === request) loading.value = false
	}
}

watch(
	() => [props.segment, props.value, JSON.stringify(props.params)],
	() => load(),
	{
		immediate: true,
	}
)

function sortBy(key) {
	if (sort.value === key) {
		descending.value = !descending.value
	} else {
		sort.value = key
		// names read best A to Z; numbers and dates largest and newest first
		descending.value = !['label', 'sales_person', 'status'].includes(key)
	}
	load()
}

function display(column, row) {
	const value = row[column.key]
	if (column.key === 'sales_person') return personLabel(value)
	if (column.key === 'kgs') {
		const kgs = formatKgs(value)
		return row.not_in_kgs ? `${kgs} · ${__('{0} not in Kg', [row.not_in_kgs])}` : kgs
	}
	if (column.key === 'value') return fullAmount(value)
	if (column.key === 'date') return value ? formatDate(value) : '—'
	return value ?? '—'
}

function open(event, row) {
	const route = ROUTES[row.doctype]?.(row.name)
	if (!route) return
	const newTab = event.ctrlKey || event.metaKey || event.shiftKey || !route.crm || !embedded
	if (newTab) {
		window.open(route.path, route.crm && !embedded ? '_self' : '_blank', 'noopener')
		return
	}
	// inside CRM the record opens in CRM's own router (the panel closes with the navigation)
	window.parent.postMessage(
		{ type: 'pranera:open-crm', path: route.path },
		window.location.origin
	)
}
</script>
