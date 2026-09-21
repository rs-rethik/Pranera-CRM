<template>
  <div v-if="kind === 'unsupported'" class="rounded-lg border border-dashed border-outline-gray-2 p-3 text-sm text-ink-gray-5">
    <span class="font-medium text-ink-gray-7">{{ label }}</span>
    can't be filled in here. Add it on the deal after converting.
  </div>

  <Link
    v-else-if="kind === 'link'"
    :model-value="modelValue || null"
    :doctype="field.options"
    :label="label"
    :placeholder="`Search ${label.toLowerCase()}`"
    :description="field.description"
    :required="!!field.reqd"
    :disabled="isDisabled"
    :error="error"
    @update:model-value="(v) => emit('update:modelValue', v || '')"
  />

  <FormControl
    v-else-if="kind === 'status' || kind === 'select'"
    type="select"
    size="md"
    :model-value="modelValue ?? ''"
    :options="selectItems"
    :label="label"
    :description="field.description"
    :required="!!field.reqd"
    :disabled="isDisabled"
    :error="error"
    placeholder="Select…"
    @update:model-value="(v) => emit('update:modelValue', v ?? '')"
  />

  <FormControl
    v-else-if="kind === 'check'"
    type="checkbox"
    :model-value="!!modelValue"
    :label="label"
    :disabled="isDisabled"
    :error="error"
    @update:model-value="(v) => emit('update:modelValue', v ? 1 : 0)"
  />

  <FormControl
    v-else-if="kind === 'number'"
    type="number"
    size="md"
    :step="field.fieldtype === 'Int' ? 1 : 'any'"
    inputmode="decimal"
    :model-value="modelValue ?? ''"
    :label="label"
    :description="field.description"
    :required="!!field.reqd"
    :disabled="isDisabled"
    :error="error"
    @update:model-value="onNumber"
  />

  <FormControl
    v-else-if="kind === 'date' || kind === 'datetime'"
    :type="kind"
    size="md"
    :model-value="modelValue || ''"
    :label="label"
    :description="field.description"
    :required="!!field.reqd"
    :disabled="isDisabled"
    :error="error"
    @update:model-value="(v) => emit('update:modelValue', v || '')"
  />

  <FormControl
    v-else-if="kind === 'textarea'"
    type="textarea"
    size="md"
    :rows="3"
    :model-value="modelValue ?? ''"
    :label="label"
    :description="field.description"
    :required="!!field.reqd"
    :disabled="isDisabled"
    :error="error"
    @update:model-value="(v) => emit('update:modelValue', v)"
  />

  <FormControl
    v-else
    :type="textType"
    size="md"
    :model-value="modelValue ?? ''"
    :label="label"
    :description="field.description"
    :required="!!field.reqd"
    :disabled="isDisabled"
    :error="error"
    @update:model-value="(v) => emit('update:modelValue', v)"
  />
</template>

<script setup>
import { computed } from 'vue'
import { FormControl } from 'frappe-ui'
import { Link } from 'frappe-ui/frappe'
import { isSupported, selectOptions } from '@/lib/layout'

const props = defineProps({
  // a DocField-like dict: { fieldname, label, fieldtype, options, reqd, read_only, description }
  field: { type: Object, required: true },
  modelValue: { type: [String, Number, Boolean, null], default: null },
  error: { type: String, default: '' },
  // CRM Deal Status rows; used to render the special-cased `status` field
  statuses: { type: Array, default: () => [] },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

const NUMBER = new Set(['Int', 'Float', 'Currency', 'Percent'])
const TEXTAREA = new Set(['Small Text', 'Text', 'Long Text', 'Text Editor', 'Markdown Editor', 'HTML Editor', 'Code', 'JSON'])

const label = computed(() => props.field.label || props.field.fieldname)
const isDisabled = computed(() => props.disabled || !!props.field.read_only)

const kind = computed(() => {
  const f = props.field
  if (!isSupported(f)) return 'unsupported'
  // CRM's own modal renders `status` as a select of deal statuses
  if (f.fieldname === 'status' && f.fieldtype === 'Link' && props.statuses.length) return 'status'
  if (f.fieldtype === 'Link' && f.options) return 'link'
  if (f.fieldtype === 'Select') return 'select'
  if (f.fieldtype === 'Check') return 'check'
  if (NUMBER.has(f.fieldtype)) return 'number'
  if (f.fieldtype === 'Date') return 'date'
  if (f.fieldtype === 'Datetime') return 'datetime'
  if (TEXTAREA.has(f.fieldtype)) return 'textarea'
  return 'text'
})

const selectItems = computed(() =>
  kind.value === 'status'
    ? props.statuses.map((s) => ({ label: s.name, value: s.name }))
    : selectOptions(props.field).map((o) => (o === '' ? { label: ' ', value: '' } : { label: o, value: o })),
)

const textType = computed(() => {
  const { fieldtype, options } = props.field
  if (options === 'Email') return 'email'
  if (options === 'URL') return 'url'
  if (fieldtype === 'Phone' || options === 'Phone') return 'tel'
  return 'text'
})

function onNumber(value) {
  if (value === '' || value === null || value === undefined) return emit('update:modelValue', null)
  const parsed = props.field.fieldtype === 'Int' ? Number.parseInt(value, 10) : Number.parseFloat(value)
  emit('update:modelValue', Number.isNaN(parsed) ? null : parsed)
}
</script>
