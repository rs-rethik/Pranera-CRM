<template>
  <div class="space-y-5">
    <h2 class="text-center text-xl font-semibold text-ink-gray-9">{{ __('Review') }}</h2>

    <ReviewCard :title="__('Lead')" :step="null" :rows="leadRows" />

    <ReviewCard
      :title="__('Organization')"
      :step="0"
      :rows="orgRows"
      :note="orgNote"
      @edit="(i) => emit('edit', i)"
    />
    <ReviewCard
      :title="__('Contact')"
      :step="1"
      :rows="contactRows"
      :note="contactNote"
      @edit="(i) => emit('edit', i)"
    />
    <ReviewCard :title="__('Deal')" :step="2" :rows="dealRows" @edit="(i) => emit('edit', i)" />
  </div>
</template>

<script setup>
import { computed, inject, toRef } from 'vue'
import ReviewCard from '@/components/ReviewCard.vue'
import { formatValue } from '@/lib/format'
import { flattenLayout, isEmpty } from '@/lib/layout'
import { __ } from '@/translation'

const emit = defineEmits(['edit'])
const w = inject('wizard')
const { ctx, form } = w
const candidates = toRef(w, 'candidates')

// Values are shown the way CRM shows them: the site's date, number and currency formats.
const show = (field, value) => (isEmpty(value) ? '\u2014' : formatValue(field, value))
const filled = (rows) => rows.filter((r) => r.value !== '\u2014')
const fieldRows = (fields, values) =>
  filled(fields.map((f) => ({ label: __(f.label || f.fieldname), value: show(f, values[f.fieldname]) })))

const leadRows = computed(() => [
  { label: __('Name'), value: show(null, ctx.lead.lead_name || ctx.lead.name) },
  { label: __('ID'), value: ctx.lead.name },
  { label: __('Status'), value: show(null, ctx.lead.status) },
])

const orgRows = computed(() => {
  const org = form.organization
  if (org.mode === 'existing') return [{ label: __('Organization'), value: org.existing }]
  if (isEmpty(org.values.organization)) {
    return [{ label: __('Organization'), value: __('None (no organization will be linked)') }]
  }
  return fieldRows(ctx.organization_fields, org.values)
})
const orgNote = computed(() =>
  form.organization.mode === 'new' && !isEmpty(form.organization.values.organization)
    ? candidates.value.auto_organization
      ? __('"{0}" already exists, so CRM will link it instead of creating a new organization.', [candidates.value.auto_organization])
      : __('A new organization will be created.')
    : '',
)

const contactRows = computed(() => {
  const contact = form.contact
  if (contact.mode === 'existing') return [{ label: __('Contact'), value: contact.existing }]
  return fieldRows(ctx.contact_fields, contact.values)
})
const contactNote = computed(() =>
  form.contact.mode === 'new'
    ? candidates.value.auto_contact
      ? __('Contact {0} already has this email or phone, so CRM will link it instead of creating a new contact.', [candidates.value.auto_contact])
      : __('A new contact will be created.')
    : '',
)

const dealRows = computed(() => {
  const rows = fieldRows(flattenLayout(ctx.deal_layout), form.deal)
  return rows.length ? rows : [{ label: __('Details'), value: __('No extra details are required.') }]
})
</script>
