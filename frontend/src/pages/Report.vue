<template>
	<!-- Shown inside CRM (crm_sidebar_ext.js opens it with ?embed=1), laid out like a CRM list page. -->
	<main class="flex h-dvh flex-col overflow-hidden bg-surface-base">
		<header
			class="flex h-10.5 shrink-0 items-center justify-between gap-2 border-b py-[7px] pl-2 pr-3 sm:pl-5 sm:pr-5"
		>
			<Breadcrumbs
				:items="[
					{ label: __('Reports'), route: { name: 'Reports', query: $route.query } },
					{ label: title },
				]"
			/>
			<div class="flex items-center gap-2">
				<!-- icon-only on phones, where the breadcrumbs need the room -->
				<template v-for="action in actions" :key="action.name">
					<Button
						class="max-sm:hidden"
						:variant="action.variant"
						:label="action.label"
						:icon-left="action.icon"
						:loading="action.loading"
						@click="action.run"
					/>
					<Button
						class="sm:hidden"
						:variant="action.variant"
						:icon="action.icon"
						:aria-label="action.label"
						:loading="action.loading"
						@click="action.run"
					/>
				</template>
				<Button
					v-if="!embedded"
					:label="__('Back to CRM')"
					icon-left="lucide-arrow-left"
					@click="goToCrm"
				/>
				<!-- inside CRM on mobile the panel covers the whole screen, so it needs a way out -->
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

		<div
			v-if="filterScriptError"
			class="mx-5 mt-4 rounded bg-surface-amber-3 px-3 py-2 text-sm text-ink-amber-7"
		>
			{{ __("Some filters of this report couldn't be loaded here, so they are not shown.") }}
		</div>

		<div v-if="hasFilters" class="flex shrink-0 flex-wrap items-center gap-4 p-5 pb-2">
			<!-- one range picker for paired from_date / to_date fields -->
			<DateRangePicker
				v-if="hasDateRangePair"
				class="!w-56"
				variant="outline"
				:model-value="dateRange"
				:placeholder="__('Date Range')"
				@update:model-value="handleDateRangeChange"
			/>

			<template v-for="filter in visibleFilters" :key="filter.fieldname">
				<Link
					v-if="filter.fieldtype === 'Link'"
					class="!w-48"
					variant="outline"
					:model-value="filterValues[filter.fieldname] || null"
					:doctype="filter.options"
					:filters="getLinkQueryFilters(filter) || undefined"
					:placeholder="filterPlaceholder(filter)"
					@update:model-value="(v) => handleFilterChange(filter.fieldname, v || null)"
				/>

				<!-- Dynamic Link: its doctype comes from another filter -->
				<Link
					v-else-if="filter.fieldtype === 'Dynamic Link' && filterValues[filter.options]"
					class="!w-48"
					variant="outline"
					:model-value="filterValues[filter.fieldname] || null"
					:doctype="filterValues[filter.options]"
					:placeholder="filterPlaceholder(filter)"
					@update:model-value="(v) => handleFilterChange(filter.fieldname, v || null)"
				/>

				<MultiLinkSelect
					v-else-if="
						filter.fieldtype === 'MultiSelectList' &&
						typeof filter.options === 'string' &&
						!filter.options.includes('\n')
					"
					class="w-60"
					:model-value="filterValues[filter.fieldname] || []"
					:doctype="filter.options"
					:filters="getLinkQueryFilters(filter)"
					:placeholder="filterPlaceholder(filter)"
					@update:model-value="(v) => handleFilterChange(filter.fieldname, v)"
				/>

				<MultiSelect
					v-else-if="filter.fieldtype === 'MultiSelectList'"
					class="w-60"
					variant="outline"
					:model-value="filterValues[filter.fieldname] || []"
					:options="getSelectOptions(filter)"
					:placeholder="filterPlaceholder(filter)"
					@update:model-value="(v) => handleFilterChange(filter.fieldname, v)"
				/>

				<FormControl
					v-else-if="['Select', 'Autocomplete'].includes(filter.fieldtype)"
					type="select"
					class="!w-48"
					:model-value="filterValues[filter.fieldname]"
					:options="getSelectOptions(filter)"
					:placeholder="filterPlaceholder(filter)"
					@update:model-value="(v) => handleFilterChange(filter.fieldname, v)"
				/>

				<FormControl
					v-else-if="['Date', 'Datetime'].includes(filter.fieldtype)"
					:type="filter.fieldtype === 'Date' ? 'date' : 'datetime-local'"
					class="!w-48"
					:model-value="filterValues[filter.fieldname]"
					:placeholder="filterPlaceholder(filter)"
					@update:model-value="(v) => handleFilterChange(filter.fieldname, v)"
				/>

				<DateRangePicker
					v-else-if="filter.fieldtype === 'DateRange'"
					class="!w-56"
					variant="outline"
					:model-value="filterValues[filter.fieldname] || []"
					:placeholder="filterPlaceholder(filter)"
					@update:model-value="
						(range) => handleFilterChange(filter.fieldname, rangeOrNull(range))
					"
				/>

				<label
					v-else-if="filter.fieldtype === 'Check'"
					class="flex cursor-pointer select-none items-center gap-2 text-sm text-ink-gray-7"
				>
					<Checkbox
						:model-value="!!filterValues[filter.fieldname]"
						@update:model-value="
							(v) => handleFilterChange(filter.fieldname, v ? 1 : 0)
						"
					/>
					<span>{{ filterPlaceholder(filter) }}</span>
				</label>

				<!-- Data / numbers / Small Text: one request once typing pauses -->
				<FormControl
					v-else-if="filter.fieldtype !== 'Dynamic Link'"
					type="text"
					class="!w-48"
					:debounce="500"
					:model-value="filterValues[filter.fieldname]"
					:placeholder="filterPlaceholder(filter)"
					@update:model-value="(v) => handleFilterChange(filter.fieldname, v)"
				/>
			</template>
		</div>

		<div class="min-h-0 flex-1 overflow-auto px-5 pb-5">
			<div
				v-if="loading && !data && !error"
				class="p-10 text-center text-sm text-ink-gray-5"
			>
				{{ __('Loading...') }}
			</div>

			<div v-else-if="error" class="p-10 text-center text-sm text-ink-red-6">
				{{ error }}
			</div>

			<div
				v-else-if="missingRequiredFilters.length"
				class="p-10 text-center text-sm text-ink-gray-5"
			>
				{{
					__('Set the required filters to run this report: {0}', [
						missingRequiredFilters.join(', '),
					])
				}}
			</div>

			<div
				v-else-if="data && data.message && !displayedRows.length"
				class="p-10 text-center text-sm text-ink-gray-5"
			>
				{{ data.message }}
			</div>

			<div
				v-else-if="!displayedRows.length"
				class="p-10 text-center text-sm text-ink-gray-5"
			>
				{{ __('No records found') }}
			</div>

			<table v-else-if="displayedColumns.length" class="w-full border-collapse text-sm">
				<thead>
					<tr class="border-b border-outline-gray-2 text-left text-ink-gray-6">
						<th
							v-for="column in displayedColumns"
							:key="column.key"
							class="whitespace-nowrap px-3 py-2 font-medium"
							:style="{ width: column.width, textAlign: column.align }"
						>
							{{ __(column.label) }}
						</th>
					</tr>
				</thead>
				<tbody>
					<!-- report rows have no reliable unique key (grouped reports repeat names) -->
					<tr
						v-for="(row, idx) in displayedRows"
						:key="idx"
						class="border-b border-outline-gray-1 hover:bg-surface-gray-1"
					>
						<td
							v-for="column in displayedColumns"
							:key="column.key"
							class="whitespace-nowrap px-3 py-2 text-ink-gray-8"
							:style="{ width: column.width, textAlign: column.align }"
						>
							<a
								v-if="recordPath(row[column.key], column)"
								:href="recordPath(row[column.key], column)"
								class="text-ink-blue-link hover:underline"
								@click="openRecord($event, recordPath(row[column.key], column))"
							>
								{{ row[column.key] }}
							</a>
							<span v-else>{{ cellValue(row, column) }}</span>
						</td>
					</tr>
				</tbody>
				<tfoot v-if="totalRow">
					<tr class="border-t-2 border-outline-gray-3 bg-surface-gray-1">
						<td
							v-for="column in displayedColumns"
							:key="column.key"
							class="whitespace-nowrap px-3 py-2 font-semibold text-ink-gray-9"
							:style="{ width: column.width, textAlign: column.align }"
						>
							{{ cellValue(totalRow, column) }}
						</td>
					</tr>
				</tfoot>
			</table>
		</div>

		<ReportPrintModal
			v-model:open="showPrintModal"
			:report-name="reportName"
			:title="title"
			:applied-filters="appliedFilters"
			:columns="columns"
			:visible-column-keys="displayedColumns.map((c) => c.key)"
			:rows="displayedRows"
			:total-row="totalRow"
			:format-value="cellValue"
		/>

		<ReportExportModal
			v-model:open="showExportModal"
			:report-name="reportName"
			:filters="filterParams"
			:applied-filters="appliedFilters"
			:columns="displayedColumns"
		/>
	</main>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import {
	Breadcrumbs,
	Button,
	Checkbox,
	DateRangePicker,
	FormControl,
	MultiSelect,
} from 'frappe-ui'
import { Link } from 'frappe-ui/frappe'
import MultiLinkSelect from '@/components/MultiLinkSelect.vue'
import ReportExportModal from '@/components/ReportExportModal.vue'
import ReportPrintModal from '@/components/ReportPrintModal.vue'
import { api, errorMessage } from '@/lib/api'
import {
	evaluateReportFiltersScript,
	formatReportValue,
	getAppliedFilters,
	getLinkQueryFilters,
	getMissingRequiredFilters,
	getRecordRoute,
	getReportFilterParams,
	isFilterVisible,
	resolveFilterDefault,
} from '@/lib/reports'
import { __ } from '@/translation'

const props = defineProps({ reportName: { type: String, required: true } })

const embedded = new URLSearchParams(window.location.search).get('embed') === '1'

const showPrintModal = ref(false)
const showExportModal = ref(false)

const meta = ref(null)
const reportFilters = ref([])
const filterValues = reactive({})
const filterScriptError = ref(false)
const dateRange = ref([])

const data = ref(null)
const columns = ref([])
const loading = ref(false)
const error = ref('')

const title = computed(() => meta.value?.report_name || props.reportName)

const actions = computed(() => [
	{
		name: 'print',
		label: __('Print'),
		icon: 'lucide-printer',
		variant: 'outline',
		run: () => (showPrintModal.value = true),
	},
	{
		name: 'export',
		label: __('Export'),
		icon: 'lucide-download',
		variant: 'outline',
		run: () => (showExportModal.value = true),
	},
	{
		name: 'refresh',
		label: __('Refresh'),
		icon: 'lucide-refresh-ccw',
		variant: 'subtle',
		loading: loading.value,
		run: runReport,
	},
])

// ---------------------------------------------------------------------------- //
// Filters
// ---------------------------------------------------------------------------- //

const hasDateRangePair = computed(() => {
	const names = reportFilters.value.map((f) => f.fieldname)
	return names.includes('from_date') && names.includes('to_date')
})

const visibleFilters = computed(() =>
	reportFilters.value.filter(
		(f) =>
			isFilterVisible(f, filterValues) &&
			!(hasDateRangePair.value && ['from_date', 'to_date'].includes(f.fieldname))
	)
)

const hasFilters = computed(() => hasDateRangePair.value || visibleFilters.value.length > 0)
const filterParams = computed(() => getReportFilterParams(reportFilters.value, filterValues))
const appliedFilters = computed(() => getAppliedFilters(reportFilters.value, filterValues))
const missingRequiredFilters = computed(() =>
	getMissingRequiredFilters(reportFilters.value, filterValues)
)

function filterPlaceholder(filter) {
	const label = __(filter.label || filter.fieldname)
	return filter.reqd ? `${label} *` : label
}

function getSelectOptions(filter) {
	if (Array.isArray(filter.options)) {
		return filter.options.map((opt) =>
			typeof opt === 'string' ? { label: opt, value: opt } : opt
		)
	}
	if (typeof filter.options === 'string') {
		return filter.options
			.split('\n')
			.filter(Boolean)
			.map((opt) => ({ label: opt, value: opt }))
	}
	return []
}

const rangeOrNull = (range) =>
	Array.isArray(range) && range.length === 2 && range[0] && range[1] ? range : null

function handleDateRangeChange(range) {
	const [from, to] = rangeOrNull(range) || []
	dateRange.value = from ? [from, to] : []
	filterValues.from_date = from || null
	filterValues.to_date = to || null
	runReport()
}

function handleFilterChange(key, value) {
	filterValues[key] = value
	runReport()
}

function initializeFilters(reportMeta) {
	let filters = []
	filterScriptError.value = false

	if (Array.isArray(reportMeta.filters) && reportMeta.filters.length) {
		// Query Report filters from the Report doc call "required" `mandatory`
		filters = reportMeta.filters.map((f) => ({ ...f, reqd: f.reqd ?? f.mandatory }))
	} else if (reportMeta.script) {
		filters = evaluateReportFiltersScript(
			reportMeta.script,
			reportMeta.name || reportMeta.report_name,
			{
				sessionUser: window.pranera_user || '',
				filterValues,
				onError: () => (filterScriptError.value = true),
			}
		)
	}

	reportFilters.value = filters
	for (const f of filters) filterValues[f.fieldname] = resolveFilterDefault(f)

	// from_date / to_date share one range picker; without defaults it starts empty
	dateRange.value =
		filterValues.from_date && filterValues.to_date
			? [filterValues.from_date, filterValues.to_date]
			: []
}

// ---------------------------------------------------------------------------- //
// Loading
// ---------------------------------------------------------------------------- //

// Only the newest request may fill the page, so a slow older response can't replace newer results.
let runId = 0

async function loadReport() {
	const id = ++runId
	reset()
	loading.value = true
	try {
		const reportMeta = await api('pranera_crm.report.get_report_meta', {
			report_name: props.reportName,
		})
		if (id !== runId) return
		meta.value = reportMeta
		initializeFilters(reportMeta)
	} catch (err) {
		if (id === runId) {
			error.value = errorMessage(err)
			loading.value = false
		}
		return
	}
	await runReport()
}

async function runReport() {
	const id = ++runId
	if (missingRequiredFilters.value.length) {
		data.value = null
		error.value = ''
		loading.value = false
		return
	}
	loading.value = true
	error.value = ''
	try {
		const result = await api('pranera_crm.report.get_report_data', {
			report_name: props.reportName,
			filters: filterParams.value,
		})
		if (id !== runId) return
		data.value = result
		columns.value = (result?.columns || []).map((c) => ({ ...c }))
	} catch (err) {
		if (id === runId) {
			data.value = null
			error.value = errorMessage(err)
		}
	} finally {
		if (id === runId) loading.value = false
	}
}

function reset() {
	data.value = null
	columns.value = []
	meta.value = null
	error.value = ''
	reportFilters.value = []
	filterScriptError.value = false
	dateRange.value = []
	Object.keys(filterValues).forEach((k) => delete filterValues[k])
}

// ---------------------------------------------------------------------------- //
// Table
// ---------------------------------------------------------------------------- //

const displayedColumns = computed(() => columns.value.filter((col) => !col.hidden))
const displayedRows = computed(() => data.value?.rows || [])
const totalRow = computed(() => data.value?.total_row || null)

function cellValue(row, column) {
	return formatReportValue(row[column.key], column, row, {
		defaultCurrency: data.value?.default_currency,
	})
}

function recordPath(value, column) {
	return getRecordRoute(value, column, meta.value?.ref_doctype)
}

// Inside CRM the record opens in CRM's own router (the panel closes with the navigation).
function openRecord(event, path) {
	if (!embedded || event.ctrlKey || event.metaKey || event.shiftKey) return
	event.preventDefault()
	window.parent.postMessage({ type: 'pranera:open-crm', path }, window.location.origin)
}

function closePanel() {
	window.parent.postMessage('pranera:close-panel', window.location.origin)
}

function goToCrm() {
	window.location.assign('/crm')
}

watch(() => props.reportName, loadReport, { immediate: true })
</script>
