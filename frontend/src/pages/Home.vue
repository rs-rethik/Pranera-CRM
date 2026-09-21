<template>
  <div class="flex min-h-dvh flex-col bg-surface-gray-1">
    <AppHeader back-href="/crm" back-label="Open CRM" />

    <main class="mx-auto w-full max-w-2xl flex-1 space-y-8 px-4 pb-10 pt-6">
      <div>
        <h1 class="text-2xl font-semibold text-ink-gray-9">Convert a lead</h1>
        <p class="mt-1 text-sm text-ink-gray-5">
          Pick a lead to walk through converting it to a deal.
        </p>
      </div>

      <section v-if="drafts.length" aria-labelledby="drafts-title">
        <h2 id="drafts-title" class="mb-2 text-sm font-semibold uppercase tracking-wide text-ink-gray-6">
          Drafts on this device
        </h2>
        <ul class="space-y-2">
          <li v-for="draft in drafts" :key="draft.lead">
            <router-link
              :to="{ name: 'Wizard', params: { name: draft.lead }, query: { step: draft.step || 1 } }"
              class="flex min-h-14 items-center gap-3 rounded-lg border border-outline-gray-2 bg-surface-white p-3 hover:bg-surface-gray-1"
            >
              <span class="lucide-file-pen-line size-5 shrink-0 text-ink-gray-5" />
              <span class="min-w-0 flex-1">
                <span class="block truncate text-base font-medium text-ink-gray-9">{{ draft.lead }}</span>
                <span class="block text-sm text-ink-gray-5">Step {{ draft.step || 1 }} · saved {{ ago(draft.savedAt) }}</span>
              </span>
              <span class="lucide-chevron-right size-4 text-ink-gray-4" />
            </router-link>
          </li>
        </ul>
      </section>

      <section aria-labelledby="leads-title">
        <h2 id="leads-title" class="mb-2 text-sm font-semibold uppercase tracking-wide text-ink-gray-6">
          Open leads
        </h2>
        <FormControl v-model="search" type="search" size="md" placeholder="Search by name, organization or ID" class="mb-3" />

        <NoticeBanner v-if="error" tone="error">{{ error }}</NoticeBanner>
        <div v-else-if="loading" class="animate-pulse space-y-2" aria-busy="true">
          <div v-for="i in 4" :key="i" class="h-14 rounded-lg bg-surface-gray-2" />
        </div>
        <p v-else-if="!leads.length" class="rounded-lg bg-surface-gray-2 p-4 text-sm text-ink-gray-6">
          No unconverted leads found.
        </p>
        <ul v-else class="space-y-2">
          <li v-for="lead in leads" :key="lead.name">
            <router-link
              :to="{ name: 'Wizard', params: { name: lead.name } }"
              class="flex min-h-14 items-center gap-3 rounded-lg border border-outline-gray-2 bg-surface-white p-3 hover:bg-surface-gray-1"
            >
              <span class="min-w-0 flex-1">
                <span class="block truncate text-base font-medium text-ink-gray-9">
                  {{ lead.lead_name || lead.first_name || lead.name }}
                </span>
                <span class="block truncate text-sm text-ink-gray-5">
                  {{ [lead.organization, lead.status, lead.name].filter(Boolean).join(' · ') }}
                </span>
              </span>
              <span class="lucide-chevron-right size-4 text-ink-gray-4" />
            </router-link>
          </li>
        </ul>
      </section>
    </main>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { FormControl } from 'frappe-ui'
import AppHeader from '@/components/AppHeader.vue'
import NoticeBanner from '@/components/NoticeBanner.vue'
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

function ago(timestamp) {
  const minutes = Math.round((Date.now() - timestamp) / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  return hours < 24 ? `${hours} h ago` : `${Math.round(hours / 24)} d ago`
}

onMounted(async () => {
  drafts.value = await listDrafts(window.pranera_user)
  fetchLeads()
})
</script>
