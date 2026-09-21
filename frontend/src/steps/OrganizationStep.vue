<template>
  <div class="space-y-4">
    <h2 class="text-center text-xl font-semibold text-ink-gray-9">Organization</h2>

    <Switch v-model="useExisting" label="Choose existing" />

    <Link
      v-if="useExisting"
      v-model="org.existing"
      doctype="CRM Organization"
      label="Organization"
      placeholder="Search organization"
      :description="matchNote"
      required
      :error="showErrors ? errors.existing : ''"
    />

    <template v-else>
      <div class="grid grid-cols-2 gap-x-4 gap-y-4">
        <FieldControl
          v-for="field in ctx.organization_fields"
          :key="field.fieldname"
          v-model="org.values[field.fieldname]"
          :field="field"
          :class="field.fieldname === 'organization' || field.fieldname === 'website' ? 'col-span-2' : ''"
          :error="showErrors ? errors[field.fieldname] : ''"
        />
      </div>
      <p v-if="candidates.auto_organization" class="text-sm text-ink-gray-5">
        "{{ candidates.auto_organization }}" already exists, so CRM will link it instead of creating a new organization.
      </p>
      <p v-else class="text-sm text-ink-gray-5">
        A new organization is created from these details. Leave the name empty to convert without one.
      </p>
    </template>
  </div>
</template>

<script setup>
import { computed, inject, toRef } from 'vue'
import { Switch } from 'frappe-ui'
import { Link } from 'frappe-ui/frappe'
import FieldControl from '@/components/FieldControl.vue'

const w = inject('wizard')
const { ctx, form } = w
const candidates = toRef(w, 'candidates')
const errors = toRef(w, 'errors')
const showErrors = toRef(w, 'showErrors')
const org = form.organization

const useExisting = computed({
  get: () => org.mode === 'existing',
  set: (on) => {
    org.mode = on ? 'existing' : 'new'
    // start from the best match so "Choose existing" is one tap
    if (on && !org.existing) {
      org.existing = candidates.value.auto_organization || candidates.value.organizations?.[0]?.name || ''
    }
  },
})

const matchNote = computed(() => {
  const match = (candidates.value.organizations || []).find((o) => o.name === org.existing)
  return match ? (match.exact ? 'Exact match with the lead' : `Matches the lead's ${match.reason}`) : ''
})
</script>
