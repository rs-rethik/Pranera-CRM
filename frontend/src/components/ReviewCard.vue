<template>
  <section class="rounded-lg border border-outline-gray-2">
    <header class="flex items-center justify-between border-b border-outline-gray-2 px-4 py-2.5">
      <h3 class="text-sm font-semibold uppercase tracking-wide text-ink-gray-6">{{ title }}</h3>
      <button
        v-if="step !== null"
        type="button"
        class="rounded-md px-2 py-1 text-sm font-medium text-ink-gray-7 hover:bg-surface-gray-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
        @click="emit('edit', step)"
      >
        Edit
      </button>
    </header>
    <dl class="divide-y divide-outline-gray-1 px-4">
      <div v-for="row in rows" :key="row.label" class="grid grid-cols-3 gap-3 py-2.5 text-sm">
        <dt class="col-span-1 text-ink-gray-5">{{ row.label }}</dt>
        <dd class="col-span-2 break-words text-ink-gray-9">{{ row.value }}</dd>
      </div>
    </dl>
    <p v-if="note" class="border-t border-outline-gray-1 px-4 py-2.5 text-sm text-ink-gray-6">{{ note }}</p>
  </section>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  step: { type: Number, default: null },
  rows: { type: Array, required: true },
  note: { type: String, default: '' },
})
const emit = defineEmits(['edit'])
</script>
