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

    <!-- the ERPNext values the wizard will assign, resolved from the questions -->
    <section v-if="customer.enabled && ctx.customer?.enabled" class="space-y-4">
      <div class="mb-1 flex items-center justify-between">
        <h3 class="text-base font-medium text-ink-gray-8">{{ __('Customer (ERPNext)') }}</h3>
        <Button variant="ghost" size="sm" @click="emit('edit', 0)">{{ __('Edit') }}</Button>
      </div>

      <p class="text-sm text-ink-gray-5">
        {{ __('Values assigned automatically from your answers. "Change" needs permission; everything is re-checked on submit.') }}
      </p>

      <div class="grid gap-x-8 gap-y-4 sm:grid-cols-2">
        <div v-for="group in valueGroups" :key="group.title" class="space-y-2">
          <p class="text-sm font-medium text-ink-gray-6">{{ group.title }}</p>
          <dl class="space-y-2 text-base">
            <div
              v-for="row in group.rows"
              :key="row.key"
              class="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1"
            >
              <dt class="shrink-0 text-ink-gray-5">
                {{ row.label }}
                <span v-if="row.was_fallback" class="text-ink-gray-4">({{ __('default') }})</span>
              </dt>
              <dd v-if="!overriding[row.key]" class="flex items-center gap-2 break-words text-end text-ink-gray-9">
                <span :class="row.overridden ? 'italic' : ''">{{ row.value ?? '\u2014' }}</span>
                <button
                  v-if="row.can_override"
                  type="button"
                  class="text-sm text-ink-gray-5 underline"
                  @click="overriding[row.key] = true"
                >
                  {{ row.value ? __('Change') : __('Set') }}
                </button>
              </dd>
              <div v-else class="w-full max-w-xs">
                <Link
                  v-if="row.fieldtype === 'Link' && row.field_options"
                  :model-value="customer.overrides[row.question_key] || null"
                  :doctype="row.field_options"
                  :placeholder="__('Select...')"
                  @update:model-value="(v) => setOverride(row, v || '')"
                />
                <FormControl
                  v-else-if="row.fieldtype === 'Select'"
                  type="select"
                  size="sm"
                  :model-value="customer.overrides[row.question_key] ?? ''"
                  :options="selectItems(row)"
                  @update:model-value="(v) => setOverride(row, v ?? '')"
                />
                <FormControl
                  v-else
                  type="text"
                  size="sm"
                  :model-value="customer.overrides[row.question_key] ?? ''"
                  @update:model-value="(v) => setOverride(row, v)"
                />
                <button type="button" class="mt-1 text-sm text-ink-gray-5 underline" @click="clearEditor(row)">
                  {{ __('Done') }}
                </button>
              </div>
            </div>
          </dl>
          <p v-if="!group.rows.length" class="text-sm text-ink-gray-4">{{ __('Nothing assigned.') }}</p>
        </div>
      </div>

      <p v-if="addressSummary" class="text-sm text-ink-gray-5">{{ addressSummary }}</p>
    </section>
  </div>
</template>

<script setup>
import { computed, inject, reactive, toRef } from 'vue'
import { Button, FormControl } from 'frappe-ui'
import { Link } from 'frappe-ui/frappe'
import ReviewCard from '@/components/ReviewCard.vue'
import { formatValue } from '@/lib/format'
import { flattenLayout, isEmpty } from '@/lib/layout'
import { resolvedFields } from '@/lib/questions'
import { __ } from '@/translation'

const emit = defineEmits(['edit'])
const w = inject('wizard')
const { ctx, form } = w
const candidates = toRef(w, 'candidates')
const customer = form.customer

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

// -- Customer (ERPNext): the resolved values, grouped by what they're written on --

const GROUP_TITLES = { Customer: __('Customer'), Address: __('Address'), Contact: __('Contact') }

const orgResolved = computed(() => resolvedFields(ctx.customer?.organization_questions, customer.answers, customer.overrides))
const contactResolved = computed(() =>
  resolvedFields(ctx.customer?.contact_questions, customer.contactAnswers, customer.overrides),
)

const valueGroups = computed(() => {
  const byDoctype = new Map()
  for (const source of [orgResolved.value, contactResolved.value]) {
    for (const row of source.rows) {
      if (!byDoctype.has(row.doctype)) byDoctype.set(row.doctype, [])
      byDoctype.get(row.doctype).push(row)
    }
  }
  const groups = [...byDoctype.entries()].map(([doctype, rows]) => ({
    title: GROUP_TITLES[doctype] || doctype,
    rows,
  }))

  const sales = [...orgResolved.value.sales_persons, ...contactResolved.value.sales_persons]
  if (sales.length) {
    groups.push({
      title: __('Sales'),
      rows: [
        {
          key: 'Customer.sales_team',
          label: __('Sales Person'),
          fieldtype: 'Link',
          field_options: 'Sales Person',
          value: [...new Set(sales.map((s) => s.value))].join(', '),
          was_fallback: false,
          overridden: sales.some((s) => s.overridden),
          can_override: sales.some((s) => s.can_override),
          question_key: sales[0].question_key,
        },
      ],
    })
  }
  return groups
})

// which rows currently show their edit control (local UI state, not persisted)
const overriding = reactive({})

function setOverride(row, value) {
  if (value) customer.overrides[row.question_key] = value
  else delete customer.overrides[row.question_key]
}

function clearEditor(row) {
  delete overriding[row.key]
}

const selectItems = (row) => [
  { label: ' ', value: '' },
  ...String(row.field_options || '')
    .split('\n')
    .map((o) => o.trim())
    .filter(Boolean)
    .map((o) => ({ label: o, value: o })),
]

const addressSummary = computed(() => {
  const a = customer.address
  const parts = [a.address_line1, a.city, a.state, a.country].filter(Boolean)
  return parts.length ? __('Address: {0}', [parts.join(', ')]) : __('No address will be added.')
})
</script>
