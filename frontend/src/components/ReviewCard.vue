<template>
  <section>
    <div class="mb-1 flex items-center justify-between">
      <h3 class="text-base font-medium text-ink-gray-8">{{ title }}</h3>
      <Button v-if="step !== null" variant="ghost" size="sm" @click="emit('edit', step)">Edit</Button>
    </div>
    <dl class="space-y-1 text-base">
      <div v-for="row in rows" :key="row.label" class="flex justify-between gap-4">
        <dt class="shrink-0 text-ink-gray-5">{{ row.label }}</dt>
        <dd class="break-words text-right text-ink-gray-9">{{ row.value }}</dd>
      </div>
    </dl>
    <p v-if="note" class="mt-1 text-sm text-ink-gray-5">{{ note }}</p>
  </section>
</template>

<script setup>
import { Button } from 'frappe-ui'

defineProps({
  title: { type: String, required: true },
  step: { type: Number, default: null },
  rows: { type: Array, required: true },
  note: { type: String, default: '' },
})
const emit = defineEmits(['edit'])
</script>
