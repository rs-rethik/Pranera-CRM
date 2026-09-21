<template>
  <div class="space-y-6">
    <StepHeading
      title="Review and confirm"
      description="Check everything below. Nothing is created until you press Convert."
    />

    <ReviewCard title="Lead" :step="null" :rows="leadRows" />

    <ReviewCard
      title="Organization"
      :step="0"
      :rows="orgRows"
      :note="orgNote"
      @edit="(i) => emit('edit', i)"
    />
    <ReviewCard
      title="Contact"
      :step="1"
      :rows="contactRows"
      :note="contactNote"
      @edit="(i) => emit('edit', i)"
    />
    <ReviewCard title="Deal" :step="2" :rows="dealRows" @edit="(i) => emit('edit', i)" />
  </div>
</template>

<script setup>
import { computed, inject, toRef } from 'vue'
import ReviewCard from '@/components/ReviewCard.vue'
import StepHeading from '@/components/StepHeading.vue'
import { flattenLayout, isEmpty } from '@/lib/layout'

const emit = defineEmits(['edit'])
const w = inject('wizard')
const { ctx, form } = w
const candidates = toRef(w, 'candidates')

const show = (v) => (isEmpty(v) ? '—' : String(v))

const leadRows = computed(() => [
  { label: 'Lead', value: show(ctx.lead.lead_name || ctx.lead.name) },
  { label: 'ID', value: ctx.lead.name },
  { label: 'Status', value: show(ctx.lead.status) },
])

const fieldRows = (fields, values) =>
  fields.map((f) => ({ label: f.label || f.fieldname, value: show(values[f.fieldname]) }))

const orgRows = computed(() => {
  const org = form.organization
  if (org.mode === 'existing') return [{ label: 'Existing organization', value: show(org.existing) }]
  if (isEmpty(org.values.organization)) return [{ label: 'Organization', value: 'None (no organization will be linked)' }]
  return fieldRows(ctx.organization_fields, org.values)
})
const orgNote = computed(() =>
  form.organization.mode === 'new' && !isEmpty(form.organization.values.organization)
    ? candidates.value.auto_organization
      ? `"${candidates.value.auto_organization}" already exists, so CRM will link it instead of creating a new one.`
      : 'A new organization will be created.'
    : '',
)

const contactRows = computed(() => {
  const contact = form.contact
  if (contact.mode === 'existing') return [{ label: 'Existing contact', value: show(contact.existing) }]
  return fieldRows(ctx.contact_fields, contact.values)
})
const contactNote = computed(() =>
  form.contact.mode === 'new'
    ? candidates.value.auto_contact
      ? `Contact ${candidates.value.auto_contact} already has this email or phone, so CRM will link it instead of creating a new one.`
      : 'A new contact will be created.'
    : '',
)

const dealRows = computed(() => {
  const rows = flattenLayout(ctx.deal_layout).map((f) => ({
    label: f.label || f.fieldname,
    value: show(form.deal[f.fieldname]),
  }))
  return rows.length ? rows : [{ label: 'Details', value: 'No extra details required' }]
})
</script>
