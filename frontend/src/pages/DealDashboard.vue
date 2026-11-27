<template>
	<!-- Shown inside CRM (crm_sidebar_ext.js opens it with ?embed=1), laid out like a CRM page. -->
	<main class="flex h-dvh flex-col overflow-hidden bg-surface-base">
		<header
			class="flex h-10.5 shrink-0 items-center justify-between gap-2 border-b py-[7px] pl-2 pr-3 sm:pl-5 sm:pr-5"
		>
			<Breadcrumbs :items="[{ label: __('Deal Dashboard') }]" />
			<div class="flex items-center gap-2">
				<span class="hidden text-sm text-ink-gray-5 sm:inline">{{ periodNote }}</span>
				<Button
					variant="ghost"
					icon="lucide-refresh-cw"
					:aria-label="__('Refresh')"
					:loading="loadingAny"
					@click="loadAll"
				/>
				<Button
					v-if="!embedded"
					:label="__('Back to CRM')"
					icon-left="lucide-arrow-left"
					@click="goToCrm"
				/>
				<Button
					v-if="embedded"
					class="sm:hidden"
					variant="ghost"
					icon="lucide-x"
					:aria-label="__('Close')"
					@click="closePanel"
				/>
			</div>
		</header>

		<div class="min-h-0 flex-1 overflow-y-auto bg-surface-gray-1">
			<div class="mx-auto flex max-w-[1400px] flex-col gap-4 px-3 py-4 sm:px-5">
				<FilterBar
					:filters="filters"
					:options="options"
					@change="setFilters"
					@reset="setFilters({ ...DEFAULTS, persons: [] })"
				/>
				<p v-if="noSalesPerson" class="text-sm text-ink-gray-6">
					{{
						__(
							'Your user is not linked to a Sales Person, so customer and order numbers are empty. Ask your manager to link your Employee to a Sales Person.'
						)
					}}
				</p>
				<p v-if="teamHead" class="text-sm text-ink-gray-6">
					{{
						__(
							"Customers and orders include your team. Deals include only those CRM shows you: your own and those assigned to you, until CRM's sales hierarchy is turned on."
						)
					}}
				</p>
				<ErrorMessage v-for="message in errors" :key="message" :message="message" />

				<h2 class="pt-1 text-lg font-semibold text-ink-gray-9">{{ __('Customers') }}</h2>
				<div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
					<KpiCard
						v-for="card in customerCards"
						:key="card.segment"
						:label="card.label"
						:value="card.value"
						:hint="card.hint"
						:loading="!data.customers"
						@open="openList(card.label, card.segment)"
					/>
				</div>
				<ChartCard
					:title="__('Customers by Sales Person')"
					:subtitle="__('Select a number to see the customers')"
					:loading="!data.customers"
					:empty="!data.customers?.by_sales_person.length"
					:empty-text="__('No active, new or potential customers for these filters.')"
					fit
				>
					<PersonTable
						:rows="data.customers.by_sales_person"
						:columns="customerColumns"
						@open="({ row, column }) => openPerson(column, row)"
					/>
				</ChartCard>

				<h2 class="pt-2 text-lg font-semibold text-ink-gray-9">{{ __('Deals') }}</h2>
				<div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
					<KpiCard
						:label="__('Pipeline')"
						:value="
							data.deals ? formatKgs(data.deals.pipeline.kgs, { short: true }) : ''
						"
						:tooltip="data.deals ? formatKgs(data.deals.pipeline.kgs) : ''"
						:hint="data.deals ? pipelineHint : ''"
						:loading="!data.deals"
						@open="openList(__('Pipeline'), 'pipeline')"
					/>
					<KpiCard
						:label="__('Delivered')"
						:value="
							data.deals ? formatKgs(delivered.current.kgs, { short: true }) : ''
						"
						:tooltip="data.deals ? formatKgs(delivered.current.kgs) : ''"
						:hint="data.deals ? deliveredHint : ''"
						:change="data.deals ? delivered.vs_previous.pct : null"
						:loading="!data.deals"
						@open="openList(__('Delivered deals'), 'delivered')"
					/>
					<KpiCard
						:label="__('Win rate')"
						:value="winRate"
						:hint="
							data.deals
								? __('{0} won · {1} lost', [
										data.deals.conversion.won,
										data.deals.conversion.lost,
								  ])
								: ''
						"
						:tooltip="
							__(
								'Order Confirmed, Dispatched or Delivered against Lost, for deals created in the period'
							)
						"
						:loading="!data.deals"
						@open="openList(__('Pipeline'), 'pipeline')"
					/>
					<KpiCard
						:label="__('Sales Orders from deals')"
						:value="data.orders ? compactAmount(data.orders.value) : ''"
						:tooltip="data.orders ? fullAmount(data.orders.value) : ''"
						:hint="data.orders ? orderHint : ''"
						:loading="!data.orders"
						@open="openList(__('Sales Orders from deals'), 'sales_orders')"
					/>
				</div>

				<div class="grid grid-cols-1 gap-3 lg:grid-cols-2">
					<ChartCard
						:title="__('Pipeline by stage')"
						:subtitle="__('Kg · deals, as of today')"
						:loading="!data.deals"
						:empty="!data.deals?.pipeline.deals"
						:empty-text="__('No open deals for these filters.')"
					>
						<ECharts
							:class="CHART"
							:options="charts.stages"
							:events="{
								click: (p) =>
									openList(
										data.deals.pipeline.by_stage[p.dataIndex].status,
										'pipeline',
										data.deals.pipeline.by_stage[p.dataIndex].status
									),
							}"
						/>
					</ChartCard>
					<ChartCard
						:title="__('Pipeline by Sales Person')"
						:subtitle="__('Kg · deals, as of today')"
						:loading="!data.deals"
						:empty="!data.deals?.pipeline.deals"
						:empty-text="__('No open deals for these filters.')"
					>
						<ECharts
							:class="CHART"
							:options="charts.people"
							:events="{
								click: (p) =>
									openPipelinePerson(
										data.deals.pipeline.by_sales_person[p.dataIndex]
									),
							}"
						/>
					</ChartCard>

					<ChartCard
						:title="__('Delivered')"
						:subtitle="trendSubtitle"
						:loading="!data.deals"
						:empty="!delivered?.current.deals"
						:empty-text="__('No deal was delivered in this period.')"
					>
						<ECharts
							:class="CHART"
							:options="charts.delivered"
							:events="{
								click: (p) =>
									openBucket(
										'delivered',
										data.deals.delivered.trend[p.dataIndex]
									),
							}"
						/>
					</ChartCard>
					<ChartCard
						:title="__('Delivered: this period against earlier ones')"
						:loading="!data.deals"
						:empty="
							!delivered ||
							!(
								delivered.current.deals ||
								delivered.previous.deals ||
								delivered.last_year.deals
							)
						"
						:empty-text="
							__(
								'No deliveries in this period, the period before or the same dates last year.'
							)
						"
					>
						<div class="flex h-full flex-col gap-2">
							<div class="flex flex-wrap gap-x-4 gap-y-1">
								<ChangeBadge
									:change="delivered.vs_previous"
									:label="__('vs previous period')"
								/>
								<ChangeBadge
									:change="delivered.vs_last_year"
									:label="__('vs same period last year')"
								/>
							</div>
							<ECharts
								:class="'min-h-0 w-full flex-1'"
								:options="charts.comparison"
							/>
						</div>
					</ChartCard>

					<ChartCard
						:title="__('Conversion by stage')"
						:subtitle="__('Deals created in the period')"
						:loading="!data.deals"
						:empty="!data.deals?.conversion.deals"
						:empty-text="__('No deals were created in this period.')"
						fit
					>
						<ConversionSteps :steps="data.deals.conversion.stages" />
					</ChartCard>
					<ChartCard
						:title="__('Sales Orders from deals')"
						:subtitle="trendSubtitle"
						:loading="!data.orders"
						:empty="!data.orders?.orders"
						:empty-text="__('No Sales Order was made from a deal in this period.')"
					>
						<ECharts
							:class="CHART"
							:options="charts.orders"
							:events="{
								click: (p) =>
									openBucket('sales_orders', data.orders.trend[p.dataIndex]),
							}"
						/>
					</ChartCard>
				</div>

				<ChartCard
					:title="__('Sales Orders from deals by Sales Person')"
					:subtitle="__('Select a number to see the orders')"
					:loading="!data.orders"
					:empty="!data.orders?.by_sales_person.length"
					:empty-text="__('No Sales Order was made from a deal in this period.')"
					fit
				>
					<PersonTable
						:rows="data.orders.by_sales_person"
						:columns="orderColumns"
						@open="
							({ row }) =>
								openList(
									personLabel(row.sales_person),
									'sales_orders',
									personValue(row.sales_person)
								)
						"
					/>
				</ChartCard>
			</div>
		</div>

		<Dialog v-model="list.open" :title="list.title" size="5xl">
			<template #default>
				<RowsTable
					v-if="list.open"
					class="max-h-[60vh]"
					:segment="list.segment"
					:value="list.value"
					:params="params"
				/>
			</template>
		</Dialog>
	</main>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Breadcrumbs, Button, Dialog, ECharts, ErrorMessage } from 'frappe-ui'
import ChangeBadge from '@/components/dashboard/ChangeBadge.vue'
import ChartCard from '@/components/dashboard/ChartCard.vue'
import ConversionSteps from '@/components/dashboard/ConversionSteps.vue'
import FilterBar from '@/components/dashboard/FilterBar.vue'
import KpiCard from '@/components/dashboard/KpiCard.vue'
import PersonTable from '@/components/dashboard/PersonTable.vue'
import RowsTable from '@/components/dashboard/RowsTable.vue'
import { apiGet, errorMessage } from '@/lib/api'
import {
	API,
	DEFAULTS,
	GRANULARITIES,
	NO_SALES_PERSON,
	apiParams,
	compactAmount,
	dateRange,
	filtersFromQuery,
	formatKgs,
	fullAmount,
	periodLabel,
	personLabel,
	queryFromFilters,
} from '@/lib/dashboard'
import {
	comparisonOptions,
	deliveredTrendOptions,
	orderTrendOptions,
	personBarsOptions,
	stageBarsOptions,
} from '@/lib/dashboardCharts'
import { formatDate } from '@/lib/format'
import { __ } from '@/translation'

const CHART = 'h-full w-full'
const SECTIONS = { customers: 'customers', deals: 'deals', orders: 'sales_orders' }

const route = useRoute()
const router = useRouter()
const embedded = route.query.embed === '1'

const filters = ref(filtersFromQuery(route.query))
const params = computed(() => apiParams(filters.value))
const options = ref({
	sales_persons: [],
	territories: [],
	sees_all: false,
	own_sales_person: null,
})
const data = reactive({ customers: null, deals: null, orders: null })
const loading = reactive({ customers: false, deals: false, orders: false })
const sectionErrors = reactive({ customers: '', deals: '', orders: '' })
const list = reactive({ open: false, title: '', segment: 'pipeline', value: '' })
const requests = { customers: 0, deals: 0, orders: 0 }

const loadingAny = computed(() => Object.values(loading).some(Boolean))
const errors = computed(() => [...new Set(Object.values(sectionErrors).filter(Boolean))])
const noSalesPerson = computed(
	() => options.value.loaded && !options.value.sees_all && !options.value.own_sales_person
)
const delivered = computed(() => data.deals?.delivered.comparison)
// someone with Sales Persons below them, who sees deals only through CRM's own rule
const teamHead = computed(
	() => options.value.loaded && !options.value.sees_all && options.value.sales_persons.length > 1
)
const periodNote = computed(() => {
	const { from, to } = dateRange(filters.value)
	return from === to ? formatDate(from) : `${formatDate(from)} – ${formatDate(to)}`
})
const trendSubtitle = computed(() => {
	const label = GRANULARITIES.find((g) => g.value === filters.value.granularity)?.label
	return __('{0}, Kg', [label])
})
const winRate = computed(() => {
	const rate = data.deals?.conversion.win_rate
	if (!data.deals) return ''
	return rate === null || rate === undefined ? '—' : `${Math.round(rate)}%`
})
const pipelineHint = computed(() => {
	const pipeline = data.deals.pipeline
	const deals = count(pipeline.deals, __('1 open deal'), __('{0} open deals'))
	const lines = count(pipeline.not_in_kgs, __('1 line not in Kg'), __('{0} lines not in Kg'))
	return pipeline.not_in_kgs ? `${deals} · ${lines}` : deals
})
const deliveredHint = computed(() => {
	const deals = count(delivered.value.current.deals, __('1 deal'), __('{0} deals'))
	// said only next to a change: without deliveries before there is nothing to compare
	return delivered.value.vs_previous.pct === null
		? deals
		: `${deals} · ${__('vs previous period')}`
})
const orderHint = computed(() => {
	const orders = data.orders
	const ordered = count(orders.orders, __('1 order'), __('{0} orders'))
	return `${ordered} · ${formatKgs(orders.kgs, { short: true })}`
})

function count(number, one, many) {
	return number === 1 ? one : many.replace('{0}', number)
}

const customerCards = computed(() => {
	const customers = data.customers
	const count = (group) => (customers ? String(customers[group].count) : '')
	return [
		{
			segment: 'active',
			label: __('Active customers'),
			value: count('active'),
			hint: customers ? __('Ordered since {0}', [formatDate(customers.active_since)]) : '',
		},
		{
			segment: 'new',
			label: __('Newly acquired'),
			value: count('new'),
			hint: __('First order in this period'),
		},
		{
			segment: 'potential',
			label: __('Potential customers'),
			value: count('potential'),
			hint: __('Open deal, no order yet'),
		},
	]
})
const customerColumns = [
	{ key: 'active', label: __('Active') },
	{ key: 'new', label: __('New') },
	{ key: 'potential', label: __('Potential') },
]
const orderColumns = [
	{ key: 'orders', label: __('Orders') },
	{
		key: 'kgs',
		label: __('Quantity'),
		format: (v) => formatKgs(v, { short: true }),
		title: (v) => formatKgs(v),
	},
	{ key: 'value', label: __('Value'), format: compactAmount, title: fullAmount },
]

// built once per load: ECharts redraws whenever its options object changes
const charts = computed(() => ({
	stages: data.deals && stageBarsOptions(data.deals.pipeline.by_stage),
	people: data.deals && personBarsOptions(data.deals.pipeline.by_sales_person),
	delivered: data.deals && deliveredTrendOptions(data.deals.delivered),
	comparison: data.deals && comparisonOptions(data.deals.delivered.comparison),
	orders: data.orders && orderTrendOptions({ ...data.orders, unit: filters.value.granularity }),
}))

async function loadSection(key) {
	const current = ++requests[key]
	loading[key] = true
	sectionErrors[key] = ''
	try {
		const result = await apiGet(`${API}.get_section`, {
			...params.value,
			section: SECTIONS[key],
		})
		if (current === requests[key]) data[key] = result
	} catch (err) {
		if (current === requests[key]) sectionErrors[key] = errorMessage(err)
	} finally {
		if (current === requests[key]) loading[key] = false
	}
}

// the three sections load side by side, so a slow one never holds up the others
function loadAll() {
	for (const key of Object.keys(SECTIONS)) loadSection(key)
}

function setFilters(next) {
	filters.value = next
	Object.assign(data, { customers: null, deals: null, orders: null }) // skeletons, not old numbers
	const query = { ...queryFromFilters(next), ...(embedded ? { embed: '1' } : {}) }
	router.replace({ query })
	// CRM keeps the filters in its own URL, so a copied link opens the same view
	if (embedded) {
		window.parent.postMessage(
			{ type: 'pranera:panel-query', query: queryFromFilters(next) },
			window.location.origin
		)
	}
}

watch(params, loadAll, { deep: true })

const personValue = (person) => person || NO_SALES_PERSON

function openList(title, segment, value = '') {
	Object.assign(list, { open: true, title, segment, value: value || '' })
}
function openPerson(column, row) {
	const card = customerCards.value.find((c) => c.segment === column.key)
	openList(
		`${card.label} · ${personLabel(row.sales_person)}`,
		column.key,
		personValue(row.sales_person)
	)
}
function openPipelinePerson(row) {
	openList(
		`${__('Pipeline')} · ${personLabel(row.sales_person)}`,
		'pipeline_person',
		personValue(row.sales_person)
	)
}
function openBucket(segment, row) {
	const title = segment === 'delivered' ? __('Delivered') : __('Sales Orders from deals')
	openList(
		`${title} · ${periodLabel(row.period, filters.value.granularity)}`,
		segment,
		row.period
	)
}

function closePanel() {
	window.parent.postMessage('pranera:close-panel', window.location.origin)
}

function goToCrm() {
	window.location.assign('/crm')
}

onMounted(async () => {
	loadAll()
	try {
		options.value = { ...(await apiGet(`${API}.get_filter_options`)), loaded: true }
	} catch {
		// the filters stay at the date ones; the sections report API errors
	}
})
</script>
