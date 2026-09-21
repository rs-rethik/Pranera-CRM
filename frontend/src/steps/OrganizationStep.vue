<template>
  <div class="space-y-5">
    <StepHeading
      title="Organization"
      description="Link the deal to an existing organization, or create one from the lead's details."
    />

    <ModeToggle v-model="org.mode" label="Organization" :options="MODES" />

    <template v-if="org.mode === 'existing'">
      <CandidateList
        v-if="items.length"
        v-model="org.existing"
        :items="items"
        label="Matching organizations"
      />
      <p v-else class="text-sm text-ink-gray-5">
        No similar organizations found. Search for one below, or switch to "Create new".
      </p>

      <Link
        v-model="org.existing"
        doctype="CRM Organization"
        label="Search organizations"
        placeholder="Type to search…"
        :error="showErrors ? errors.existing : ''"
      />
    </template>

    <template v-else>
      <NoticeBanner v-if="candidates.auto_organization" tone="warning">
        An organization named
        <strong>{{ candidates.auto_organization }}</strong>
        already exists. CRM links that one instead of creating a duplicate.
        <template #action>
          <Button size="sm" variant="subtle" @click="useAuto">Use it</Button>
        </template>
      </NoticeBanner>

      <div class="grid gap-4 sm:grid-cols-2">
        <FieldControl
          v-for="field in ctx.organization_fields"
          :key="field.fieldname"
          v-model="org.values[field.fieldname]"
          :field="field"
          :class="field.fieldname === 'organization' ? 'sm:col-span-2' : ''"
          :error="showErrors ? errors[field.fieldname] : ''"
        />
      </div>
      <p class="text-sm text-ink-gray-5">
        Leave the organization name empty to convert without an organization.
      </p>
    </template>
  </div>
</template>

<script setup>
import { computed, inject, toRef } from 'vue'
import { Button } from 'frappe-ui'
import { Link } from 'frappe-ui/frappe'
import CandidateList from '@/components/CandidateList.vue'
import FieldControl from '@/components/FieldControl.vue'
import ModeToggle from '@/components/ModeToggle.vue'
import NoticeBanner from '@/components/NoticeBanner.vue'
import StepHeading from '@/components/StepHeading.vue'

const w = inject('wizard')
const { ctx, form } = w
const candidates = toRef(w, 'candidates')
const errors = toRef(w, 'errors')
const showErrors = toRef(w, 'showErrors')
const org = form.organization

const MODES = [
  { value: 'existing', label: 'Use existing' },
  { value: 'new', label: 'Create new' },
]

const items = computed(() =>
  (candidates.value.organizations || []).map((o) => ({
    name: o.name,
    title: o.organization_name || o.name,
    subtitle: [o.website, o.industry].filter(Boolean).join(' · '),
    badge: o.exact ? 'Exact match' : `Matches ${o.reason}`,
  })),
)

function useAuto() {
  org.existing = candidates.value.auto_organization
  org.mode = 'existing'
}
</script>
