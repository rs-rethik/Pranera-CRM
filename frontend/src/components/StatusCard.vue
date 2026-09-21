<template>
  <div class="mx-auto mt-8 max-w-md rounded-xl border border-outline-gray-2 bg-surface-white p-6 text-center">
    <span :class="icon" class="mx-auto size-10 text-ink-gray-6" aria-hidden="true" />
    <h2 class="mt-3 text-xl font-semibold text-ink-gray-9">{{ title }}</h2>
    <p class="mt-1 text-sm text-ink-gray-6">{{ text }}</p>
    <div class="mt-5 flex justify-center gap-2"><slot /></div>
  </div>
</template>

<script setup>
defineProps({
  icon: { type: String, required: true },
  title: { type: String, required: true },
  text: { type: String, default: '' },
})
</script>
