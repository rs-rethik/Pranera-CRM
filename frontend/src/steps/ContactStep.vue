<template>
  <div class="space-y-5">
    <StepHeading
      title="Contact"
      description="Link the deal to an existing contact, or create one from the lead's details."
    />

    <ModeToggle v-model="contact.mode" label="Contact source" :options="MODES" />

    <template v-if="contact.mode === 'existing'">
      <CandidateList
        v-if="items.length"
        v-model="contact.existing"
        :items="items"
        label="Matching contacts"
      />
      <p v-else class="text-sm text-ink-gray-5">
        No contact with the lead's email or phone was found. Search for one below, or switch to "Create new".
      </p>
      <div class="pt-2">
        <Link
          v-model="contact.existing"
          doctype="Contact"
          label="Search contacts"
          placeholder="Type to search…"
          :error="showErrors ? errors.existing : ''"
        />
      </div>
    </template>

    <template v-else>
      <NoticeBanner v-if="candidates.auto_contact" tone="warning">
        A contact with this email or phone already exists
        (<strong>{{ candidates.auto_contact }}</strong>). CRM links it instead of creating a duplicate.
        <template #action>
          <Button size="sm" variant="subtle" @click="useAuto">Use it</Button>
        </template>
      </NoticeBanner>

      <div class="grid gap-4 sm:grid-cols-2">
        <FieldControl
          v-for="field in ctx.contact_fields"
          :key="field.fieldname"
          v-model="contact.values[field.fieldname]"
          :field="{ ...field, reqd: field.fieldname === 'first_name' ? 1 : field.reqd }"
          :error="showErrors ? errors[field.fieldname] : ''"
        />
      </div>
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
const contact = form.contact

const MODES = [
  { value: 'existing', label: 'Use existing' },
  { value: 'new', label: 'Create new' },
]

const items = computed(() =>
  (candidates.value.contacts || []).map((c) => ({
    name: c.name,
    title: [c.first_name, c.last_name].filter(Boolean).join(' ') || c.name,
    subtitle: [c.email_id, c.mobile_no, c.company_name].filter(Boolean).join(' · '),
    badge: `Matches ${c.reason}`,
  })),
)

function useAuto() {
  contact.existing = candidates.value.auto_contact
  contact.mode = 'existing'
}
</script>
