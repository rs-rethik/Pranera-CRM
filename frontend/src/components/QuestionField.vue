<template>
  <FormControl
    type="select"
    size="sm"
    :model-value="modelValue ?? defaultValue ?? ''"
    :options="selectItems"
    :label="question.label"
    :placeholder="__('Select...')"
    :error="error"
    @update:model-value="(v) => emit('update:modelValue', v ?? '')"
  />
</template>

<script setup>
import { computed } from 'vue'
import { FormControl } from 'frappe-ui'
import { defaultAnswer } from '@/lib/questions'
import { __ } from '@/translation'

const props = defineProps({
  // one entry from get_wizard_context's organization_questions / contact_questions,
  // or refresh_customer_questions's response for a single scope
  question: { type: Object, required: true },
  modelValue: { type: String, default: null },
  error: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])

const defaultValue = computed(() => defaultAnswer(props.question))

const selectItems = computed(() => [
  { label: ' ', value: '' },
  ...(props.question.options || []).map((o) => ({ label: o.label, value: o.value })),
])
</script>
