<template>
	<!-- Shown inside CRM (crm_sidebar_ext.js opens it with ?embed=1): the reports in the user's
	     sidebar, and where to add or remove them. -->
	<main class="flex h-dvh flex-col bg-surface-base">
		<header
			class="flex h-10.5 shrink-0 items-center justify-between gap-2 border-b py-[7px] pl-2 pr-3 sm:pl-5 sm:pr-5"
		>
			<Breadcrumbs :items="[{ label: __('Reports') }]" />
			<div class="flex items-center gap-2">
				<Button
					variant="solid"
					:label="__('Add Existing Report')"
					icon-left="lucide-plus"
					@click="openAddModal"
				/>
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

		<div class="min-h-0 flex-1 overflow-y-auto px-3 py-6 sm:px-5">
			<p class="mb-4 text-p-base text-ink-gray-6">
				{{
					__(
						'Reports under the FCRM module that you add here are shown in your CRM sidebar.'
					)
				}}
			</p>

			<ErrorMessage class="mb-3" :message="error" />

			<LoadingText v-if="loadingPinned && !pinned" :text="__('Loading...')" />

			<div
				v-else-if="!pinned?.length"
				class="flex flex-col items-center justify-center rounded-lg border border-dashed border-outline-gray-2 bg-surface-gray-1 p-8 py-16 text-center"
			>
				<span class="lucide-file-text mb-3 size-8 text-ink-gray-5" aria-hidden="true" />
				<div class="mb-1 text-base font-medium text-ink-gray-8">
					{{ __('No reports configured') }}
				</div>
				<p class="mb-4 max-w-sm text-sm text-ink-gray-5">
					{{
						__(
							'Add existing reports from the FCRM module to open them from your CRM sidebar.'
						)
					}}
				</p>
				<Button
					variant="subtle"
					:label="__('Add Existing Report')"
					icon-left="lucide-plus"
					@click="openAddModal"
				/>
			</div>

			<ul v-else class="flex flex-col divide-y divide-outline-gray-1">
				<li
					v-for="report in pinned"
					:key="report.report"
					class="group flex items-center justify-between gap-3 rounded-lg px-2 py-3 hover:bg-surface-gray-2"
				>
					<router-link
						:to="{
							name: 'Report',
							params: { reportName: report.report },
							query: $route.query,
						}"
						class="flex min-w-0 flex-1 items-center gap-3"
					>
						<span
							class="grid size-8 shrink-0 place-items-center rounded bg-surface-gray-2 text-ink-gray-6"
						>
							<span class="lucide-file-text size-4" aria-hidden="true" />
						</span>
						<span class="flex min-w-0 flex-col">
							<span class="truncate text-base font-medium text-ink-gray-8">{{
								report.title || report.report
							}}</span>
							<span class="truncate text-xs text-ink-gray-5">{{
								report.report
							}}</span>
						</span>
					</router-link>
					<Button
						variant="ghost"
						theme="red"
						:label="__('Remove')"
						:loading="removing === report.report"
						@click="removeReport(report)"
					/>
				</li>
			</ul>
		</div>

		<Dialog
			v-model="showAddModal"
			:title="__('Add Existing Report')"
			size="lg"
			@close="closeAddModal"
		>
			<template #default>
				<div class="flex flex-col gap-4">
					<p class="text-sm text-ink-gray-6">
						{{
							__(
								'Select existing reports from the FCRM module to add to your sidebar.'
							)
						}}
					</p>

					<FormControl
						v-if="unadded.length > 5 || search"
						v-model="search"
						type="search"
						:placeholder="__('Search reports...')"
					/>

					<LoadingText v-if="loadingAvailable && !available" :text="__('Loading...')" />

					<div
						v-else-if="!available?.length"
						class="py-8 text-center text-sm text-ink-gray-5"
					>
						{{
							__(
								'No reports found under the FCRM module. Create a Query Report or Script Report in Desk with module "FCRM" to see it here.'
							)
						}}
					</div>

					<div
						v-else-if="!unadded.length"
						class="py-8 text-center text-sm text-ink-gray-5"
					>
						{{ __('All available reports have already been added to your sidebar.') }}
					</div>

					<div v-else class="flex max-h-80 flex-col gap-1 overflow-y-auto pr-1">
						<div
							v-if="filtered.length > 1"
							class="mb-1 flex cursor-pointer select-none items-center justify-between rounded-md bg-surface-gray-2 px-3 py-2 text-xs font-medium text-ink-gray-6"
							@click="toggleSelectAll"
						>
							<span class="flex items-center gap-2">
								<Checkbox
									:model-value="isAllSelected"
									@click.stop="toggleSelectAll"
								/>
								<span>{{ __('Select All') }}</span>
							</span>
							<span class="text-ink-gray-5">
								{{ __('{0} / {1} selected', [selected.length, filtered.length]) }}
							</span>
						</div>

						<div
							v-for="report in filtered"
							:key="report.name"
							class="flex cursor-pointer select-none items-center gap-3 rounded-md px-3 py-2.5 hover:bg-surface-gray-2"
							@click="toggleSelected(report.name)"
						>
							<Checkbox
								:model-value="selected.includes(report.name)"
								@click.stop
								@update:model-value="toggleSelected(report.name)"
							/>
							<div class="flex min-w-0 flex-col">
								<div class="truncate text-sm font-medium text-ink-gray-8">
									{{ report.title || report.name }}
								</div>
								<div class="truncate text-xs text-ink-gray-5">
									{{ report.report_type }}
								</div>
							</div>
						</div>
					</div>
				</div>
			</template>

			<template #actions>
				<div class="flex items-center justify-end gap-2">
					<Button variant="outline" :label="__('Cancel')" @click="closeAddModal" />
					<Button
						variant="solid"
						:label="__('Save')"
						:disabled="!selected.length || saving"
						:loading="saving"
						@click="saveReports"
					/>
				</div>
			</template>
		</Dialog>
	</main>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import {
	Breadcrumbs,
	Button,
	Checkbox,
	Dialog,
	ErrorMessage,
	FormControl,
	LoadingText,
	toast,
} from 'frappe-ui'
import { api, errorMessage } from '@/lib/api'
import { __ } from '@/translation'

const embedded = new URLSearchParams(window.location.search).get('embed') === '1'

const pinned = ref(null)
const available = ref(null)
const loadingPinned = ref(true)
const loadingAvailable = ref(false)
const error = ref('')

const showAddModal = ref(false)
const selected = ref([])
const search = ref('')
const saving = ref(false)
const removing = ref(null)

const pinnedNames = computed(() => new Set((pinned.value || []).map((r) => r.report)))
const unadded = computed(() =>
	(available.value || []).filter((r) => !pinnedNames.value.has(r.name) && !r.pinned)
)
const filtered = computed(() => {
	const query = search.value.trim().toLowerCase()
	if (!query) return unadded.value
	return unadded.value.filter(
		(r) =>
			r.name.toLowerCase().includes(query) ||
			(r.title && r.title.toLowerCase().includes(query))
	)
})
const isAllSelected = computed(
	() => filtered.value.length > 0 && filtered.value.every((r) => selected.value.includes(r.name))
)

async function loadPinned() {
	loadingPinned.value = true
	try {
		pinned.value = await api('pranera_crm.report.get_pinned_reports')
		error.value = ''
	} catch (err) {
		error.value = errorMessage(err)
	} finally {
		loadingPinned.value = false
	}
}

async function loadAvailable() {
	loadingAvailable.value = true
	try {
		available.value = await api('pranera_crm.report.get_fcrm_reports')
	} catch (err) {
		error.value = errorMessage(err)
	} finally {
		loadingAvailable.value = false
	}
}

// tells CRM's sidebar to show the new list
const notifySidebar = () =>
	window.parent.postMessage({ type: 'pranera:pins-changed' }, window.location.origin)

function openAddModal() {
	selected.value = []
	search.value = ''
	loadAvailable()
	showAddModal.value = true
}

function closeAddModal() {
	showAddModal.value = false
	selected.value = []
	search.value = ''
}

function toggleSelected(name) {
	const index = selected.value.indexOf(name)
	if (index === -1) selected.value.push(name)
	else selected.value.splice(index, 1)
}

function toggleSelectAll() {
	const names = filtered.value.map((r) => r.name)
	if (isAllSelected.value) {
		selected.value = selected.value.filter((name) => !names.includes(name))
	} else {
		selected.value = [...new Set([...selected.value, ...names])]
	}
}

async function saveReports() {
	if (!selected.value.length || saving.value) return
	saving.value = true
	try {
		const reports = selected.value.map((name) => ({ report: name, icon: 'lucide-file-text' }))
		const { added = [], skipped = [] } =
			(await api('pranera_crm.report.pin_reports', { reports })) || {}
		if (added.length) toast.success(__('{0} report(s) added', [added.length]))
		// tell the user which ones weren't added, and why
		for (const { report, reason } of skipped)
			toast.error(__("Couldn't add {0}: {1}", [report, reason]))
		closeAddModal()
		await loadPinned()
		notifySidebar()
	} catch (err) {
		toast.error(errorMessage(err))
	} finally {
		saving.value = false
	}
}

async function removeReport(report) {
	removing.value = report.report
	try {
		await api('pranera_crm.report.unpin_report', { report: report.report })
		toast.success(__('Report removed successfully'))
		await loadPinned()
		notifySidebar()
	} catch (err) {
		toast.error(errorMessage(err))
	} finally {
		removing.value = null
	}
}

function closePanel() {
	window.parent.postMessage('pranera:close-panel', window.location.origin)
}

function goToCrm() {
	window.location.assign('/crm')
}

onMounted(loadPinned)
</script>
