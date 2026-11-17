<template>
	<main
		class="min-h-dvh bg-surface-base px-4 pb-[max(1.5rem,env(safe-area-inset-bottom))] pt-[max(2rem,env(safe-area-inset-top))] sm:pt-[8vh]"
	>
		<div
			class="mx-auto w-full max-w-md rounded-lg border border-outline-gray-2 bg-surface-base p-5 sm:px-10 sm:py-8"
		>
			<h1 class="mb-6 text-center text-xl font-semibold text-ink-gray-9">
				{{ __('Convert a lead') }}
			</h1>

			<div v-if="drafts.length" class="mb-6">
				<h2 class="mb-1 text-base font-medium text-ink-gray-8">{{ __('Drafts') }}</h2>
				<ul>
					<li v-for="draft in drafts" :key="draft.lead">
						<router-link
							:to="{
								name: 'Wizard',
								params: { name: draft.lead },
								query: { step: draft.step || 1 },
							}"
							class="flex justify-between gap-4 py-1.5 text-base text-ink-gray-9 hover:underline"
						>
							<span class="truncate">{{ draft.lead }}</span>
							<span class="shrink-0 text-ink-gray-5">{{
								__('Step {0}', [draft.step || 1])
							}}</span>
						</router-link>
					</li>
				</ul>
			</div>

			<FormControl
				v-model="search"
				type="text"
				size="sm"
				:label="__('Lead')"
				:placeholder="__('Search by name, organization or ID')"
			/>

			<div class="mt-4">
				<ErrorMessage :message="error" />
				<LoadingText v-if="loading" :text="__('Loading...')" />
				<p v-else-if="!error && !leads.length" class="text-sm text-ink-gray-5">
					{{ __('No unconverted leads found.') }}
				</p>
				<ul v-else>
					<li v-for="lead in leads" :key="lead.name">
						<router-link
							:to="{ name: 'Wizard', params: { name: lead.name } }"
							class="flex justify-between gap-4 py-1.5 text-base text-ink-gray-9 hover:underline"
						>
							<span class="truncate">{{
								lead.lead_name || lead.first_name || lead.name
							}}</span>
							<span class="shrink-0 truncate text-ink-gray-5">{{
								lead.organization || lead.name
							}}</span>
						</router-link>
					</li>
				</ul>
			</div>
		</div>
	</main>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { ErrorMessage, FormControl, LoadingText } from 'frappe-ui'
import { api, errorMessage } from '@/lib/api'
import { debounce } from '@/lib/debounce'
import { listDrafts } from '@/lib/drafts'

const leads = ref([])
const drafts = ref([])
const search = ref('')
const loading = ref(true)
const error = ref('')

async function fetchLeads() {
	loading.value = true
	error.value = ''
	const q = search.value.trim()
	try {
		leads.value = await api('frappe.client.get_list', {
			doctype: 'CRM Lead',
			fields: ['name', 'lead_name', 'first_name', 'organization', 'status', 'modified'],
			filters: { converted: 0 },
			or_filters: q
				? [
						['lead_name', 'like', `%${q}%`],
						['organization', 'like', `%${q}%`],
						['name', 'like', `%${q}%`],
				  ]
				: undefined,
			order_by: 'modified desc',
			limit_page_length: 25,
		})
	} catch (err) {
		error.value = errorMessage(err)
	} finally {
		loading.value = false
	}
}

const debouncedFetch = debounce(fetchLeads, 350)
watch(search, () => debouncedFetch())

onMounted(async () => {
	drafts.value = await listDrafts(window.pranera_user)
	fetchLeads()
})
</script>
