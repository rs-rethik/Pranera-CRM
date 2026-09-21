<template>
  <div class="space-y-4">
    <h2 class="text-center text-xl font-semibold text-ink-gray-9">Contact</h2>

    <Switch v-model="useExisting" label="Choose existing" />

    <Link
      v-if="useExisting"
      v-model="contact.existing"
      doctype="Contact"
      label="Contact"
      placeholder="Search contact"
      :description="matchNote"
      required
      :error="showErrors ? errors.existing : ''"
    />

    <template v-else>
      <div class="grid grid-cols-2 gap-x-4 gap-y-4">
        <FieldControl
          v-for="field in fields"
          :key="field.fieldname"
          v-model="contact.values[field.fieldname]"
          :field="{ ...field, reqd: field.fieldname === 'first_name' ? 1 : field.reqd }"
          :class="FULL_WIDTH.includes(field.fieldname) ? 'col-span-2' : ''"
          :error="showErrors ? errors[field.fieldname] : ''"
        />
      </div>
      <p v-if="candidates.auto_contact" class="text-sm text-ink-gray-5">
        Contact {{ candidates.auto_contact }} already has this email or phone, so CRM will link it instead of creating a new contact.
      </p>
      <p v-else class="text-sm text-ink-gray-5">A new contact is created from these details.</p>
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
const contact = form.contact

// display order: pairs share a row, these span the full width
const ORDER = ['salutation', 'gender', 'first_name', 'last_name', 'email', 'phone', 'mobile_no', 'job_title']
const FULL_WIDTH = ['email', 'job_title']
const fields = computed(() =>
  [...ctx.contact_fields].sort((a, b) => ORDER.indexOf(a.fieldname) - ORDER.indexOf(b.fieldname)),
)

const useExisting = computed({
  get: () => contact.mode === 'existing',
  set: (on) => {
    contact.mode = on ? 'existing' : 'new'
    if (on && !contact.existing) {
      contact.existing = candidates.value.auto_contact || candidates.value.contacts?.[0]?.name || ''
    }
  },
})

const matchNote = computed(() => {
  const match = (candidates.value.contacts || []).find((c) => c.name === contact.existing)
  return match ? `Matches the lead's ${match.reason}` : ''
})
</script>
